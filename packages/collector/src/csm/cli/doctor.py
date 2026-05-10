"""``csm doctor`` — diagnostic report.

Each check is a small ``(name, ok, detail)`` tuple. Output a human-readable
report; exit 0 if all green, 1 otherwise.

The optional ``--gate-test`` flag fires a synthetic ``SessionStart`` hook
through the running collector and verifies the row landed in ``events``,
satisfying spec acceptance criterion #1.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import typer

from csm import crypto
from csm.cli.hooks import HOOK_EVENTS, hook_script_path
from csm.cli.launchd import plist_install_path
from csm.config import Paths
from csm.db import connect


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _check_hooks_installed(settings_path: Path, script_path: Path) -> CheckResult:
    if not settings_path.exists():
        return CheckResult("hooks installed", False, f"{settings_path} does not exist")
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        return CheckResult("hooks installed", False, f"{settings_path} not valid JSON: {exc}")
    hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
    if not isinstance(hooks, dict):
        return CheckResult("hooks installed", False, "settings.hooks is not an object")
    missing = []
    for ev in HOOK_EVENTS:
        block = hooks.get(ev) or []
        if not any(
            isinstance(entry, dict)
            and any(
                isinstance(h, dict) and str(h.get("command", "")).startswith(str(script_path))
                for h in entry.get("hooks", [])
            )
            for entry in block
        ):
            missing.append(ev)
    if missing:
        return CheckResult("hooks installed", False, f"missing entries for: {', '.join(missing)}")
    return CheckResult("hooks installed", True, str(settings_path))


def _check_launchd_plist() -> CheckResult:
    p = plist_install_path()
    if p.exists():
        return CheckResult("launchd plist present", True, str(p))
    return CheckResult("launchd plist present", False, f"{p} not found")


def _check_collector_reachable(host: str = "127.0.0.1", port: int = 8765) -> CheckResult:
    url = f"http://{host}:{port}/healthz"
    try:
        resp = httpx.get(url, timeout=1.0)
    except httpx.HTTPError as exc:
        return CheckResult("collector reachable", False, f"{url}: {exc.__class__.__name__}")
    if resp.status_code == 200:
        return CheckResult("collector reachable", True, url)
    return CheckResult("collector reachable", False, f"{url} returned {resp.status_code}")


def _check_ntfy_topic_set(*, key: bytes | None) -> CheckResult:
    paths = Paths.from_env()
    if not paths.db.exists():
        return CheckResult("ntfy topic set", False, "DB does not exist yet")
    try:
        conn = connect(key=key, db_path=paths.db)
    except Exception as exc:  # broad: sqlcipher3.DatabaseError or anything else
        return CheckResult("ntfy topic set", False, f"DB open failed: {exc.__class__.__name__}")
    try:
        row = conn.execute("SELECT value FROM settings WHERE key='ntfy_topic'").fetchone()
    finally:
        conn.close()
    topic = row[0] if row else ""
    if topic:
        return CheckResult("ntfy topic set", True, topic)
    return CheckResult("ntfy topic set", False, "(empty — push notifications disabled)")


def _check_keychain_key() -> CheckResult:
    try:
        key = crypto.get_key_from_keychain()
    except Exception as exc:  # keyring may raise on locked Keychain
        return CheckResult("keychain key", False, f"{exc.__class__.__name__}: {exc}")
    if key is None:
        return CheckResult("keychain key", False, "no entry found")
    return CheckResult("keychain key", True, "present")


def _check_sqlcipher() -> CheckResult:
    try:
        import sqlcipher3  # noqa: F401  (probe)
    except ImportError as exc:
        return CheckResult("sqlcipher available", False, f"import failed: {exc}")
    return CheckResult("sqlcipher available", True, "import ok")


def _gate_test(*, host: str, port: int, key: bytes | None) -> CheckResult:
    """Fire a synthetic SessionStart and verify the events row.

    Uses a generated session_id so we can find the row deterministically,
    then opens the DB to confirm the receiver wrote the event.
    """
    paths = Paths.from_env()
    if not paths.db.exists():
        return CheckResult("gate test", False, "DB does not exist yet")

    session_id = f"doctor-gate-{uuid.uuid4()}"
    payload: dict[str, Any] = {
        "session_id": session_id,
        "transcript_path": "/tmp/csm-doctor-gate-transcript.jsonl",
        "cwd": "/tmp",
        "source": "startup",
    }
    url = f"http://{host}:{port}/hook/SessionStart"
    try:
        resp = httpx.post(url, json=payload, timeout=2.0)
    except httpx.HTTPError as exc:
        return CheckResult("gate test", False, f"POST {url}: {exc.__class__.__name__}")
    if resp.status_code != 200:
        return CheckResult("gate test", False, f"POST {url} -> {resp.status_code}")

    # Verify it landed.
    try:
        conn = connect(key=key, db_path=paths.db)
    except Exception as exc:
        return CheckResult("gate test", False, f"DB open failed: {exc.__class__.__name__}")
    try:
        row = conn.execute(
            "SELECT count(*) FROM events WHERE session_id=? AND event_name='SessionStart'",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    count = row[0] if row else 0
    if count > 0:
        return CheckResult("gate test", True, f"event landed (session={session_id})")
    return CheckResult("gate test", False, f"event not found for session={session_id}")


def doctor_command(
    gate_test: bool = typer.Option(
        False,
        "--gate-test",
        help="Fire a synthetic SessionStart hook and verify it landed in events.",
    ),
) -> None:
    """Print a health report. Exit code 0 if all checks pass, 1 otherwise."""
    paths = Paths.from_env()
    key = crypto.get_key_from_keychain()

    checks: list[CheckResult] = [
        _check_hooks_installed(paths.settings_json, hook_script_path()),
        _check_launchd_plist(),
        _check_collector_reachable(),
        _check_keychain_key(),
        _check_sqlcipher(),
        _check_ntfy_topic_set(key=key),
    ]

    if gate_test:
        checks.append(_gate_test(host="127.0.0.1", port=8765, key=key))

    typer.echo("csm doctor")
    typer.echo("==========")
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    typer.echo(f"checked at {timestamp}")
    typer.echo("")
    for c in checks:
        marker = "[ok]" if c.ok else "[x ]"
        typer.echo(f"  {marker} {c.name}: {c.detail}")
    typer.echo("")
    if all(c.ok for c in checks):
        typer.echo("All checks passed.")
        raise typer.Exit(code=0)
    typer.echo("One or more checks failed.")
    raise typer.Exit(code=1)
