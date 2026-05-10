"""``csm install-hooks`` — idempotent merger into ``~/.claude/settings.json``.

Per spec §11.12 (and the "carry-forward lessons learned" #3): always back
up the user's settings file with a timestamped suffix before writing. The
merge logic preserves any unrelated keys; we only add/remove our own
``{"matcher": "", "hooks": [{"type": "command", "command": "<csm-hook>"}]}``
entry under each of the supported hook event keys.

The path can be overridden via the ``CSM_CLAUDE_SETTINGS`` env var
(captured by :class:`csm.config.Paths`). Tests use that hook so they
never touch the user's real config.

The shell-script body lives in :mod:`csm.cli._hook_script` so it ships
with the wheel.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from csm.cli._hook_script import HOOK_SCRIPT
from csm.config import Paths

# All hook events we register against — same set the receiver knows about.
HOOK_EVENTS: tuple[str, ...] = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "Stop",
    "SubagentStop",
    "SessionEnd",
    "PreCompact",
    "Setup",
)


def hook_script_path() -> Path:
    """Canonical install location for the bundled shell script."""
    return Path.home() / ".csm" / "csm-hook.sh"


def _hook_command(script_path: Path, event_name: str) -> str:
    """Shell command Claude Code will exec for this hook.

    The script takes the event name as ``$1`` so a single script handles
    every event.
    """
    return f"{script_path} {event_name}"


def _hook_entry(script_path: Path, event_name: str) -> dict[str, Any]:
    return {
        "matcher": "",
        "hooks": [
            {"type": "command", "command": _hook_command(script_path, event_name)},
        ],
    }


def _is_csm_entry(entry: dict[str, Any], script_path: Path) -> bool:
    """Detect a hook entry that we own.

    Detection is based on the command string starting with our installed
    script path; this is robust across argument-list growth in future
    versions.
    """
    hooks = entry.get("hooks") or []
    for h in hooks:
        cmd = h.get("command", "") if isinstance(h, dict) else ""
        if isinstance(cmd, str) and cmd.startswith(str(script_path)):
            return True
    return False


@dataclass(frozen=True)
class HookInstallResult:
    settings_path: Path
    backup_path: Path | None
    script_path: Path
    changed: bool
    diff: str


def _render_diff(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Render a tiny human-readable diff between two settings dicts.

    We don't pull in ``difflib`` — the hooks block is small and a
    side-by-side JSON dump is the most useful thing for a dry-run.
    """
    return (
        "--- before\n"
        f"{json.dumps(before.get('hooks', {}), indent=2, sort_keys=True)}\n"
        "+++ after\n"
        f"{json.dumps(after.get('hooks', {}), indent=2, sort_keys=True)}\n"
    )


def _load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded: Any = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise typer.BadParameter(f"{path} top-level value must be a JSON object")
    return loaded


def _backup(path: Path) -> Path:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak.{timestamp}")
    shutil.copy2(path, backup)
    return backup


def _write_hook_script(script_path: Path) -> None:
    script_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    script_path.write_text(HOOK_SCRIPT, encoding="utf-8")
    script_path.chmod(0o755)


def install_hooks(
    *,
    settings_path: Path | None = None,
    script_path: Path | None = None,
    dry_run: bool = False,
    uninstall: bool = False,
) -> HookInstallResult:
    """Idempotently install (or remove) csm hook entries.

    Args:
        settings_path: Override for ``~/.claude/settings.json``. Defaults
            to ``Paths.from_env().settings_json``.
        script_path: Override for ``~/.csm/csm-hook.sh``.
        dry_run: When True, compute the changes and return a diff but
            don't write to disk.
        uninstall: When True, remove our entries (preserving any
            unrelated user hooks).

    The function is idempotent: re-running with the same args on an
    already-installed config produces ``changed=False`` and no backup.
    """
    settings_path = settings_path or Paths.from_env().settings_json
    script_path = script_path or hook_script_path()

    before = _load_settings(settings_path)
    after = json.loads(json.dumps(before))  # deep-copy via round-trip

    hooks_block: dict[str, Any] = after.setdefault("hooks", {})

    for event_name in HOOK_EVENTS:
        existing = hooks_block.get(event_name)
        if not isinstance(existing, list):
            existing = []

        # Drop any of our previous entries — we'll re-add unless uninstalling.
        kept = [
            entry
            for entry in existing
            if isinstance(entry, dict) and not _is_csm_entry(entry, script_path)
        ]

        if uninstall:
            if kept:
                hooks_block[event_name] = kept
            else:
                # No unrelated entries left and nothing of ours either —
                # remove the key entirely so we don't leave empty arrays.
                hooks_block.pop(event_name, None)
        else:
            kept.append(_hook_entry(script_path, event_name))
            hooks_block[event_name] = kept

    # Clean up empty hooks block on uninstall so the file isn't littered.
    if uninstall and not hooks_block:
        after.pop("hooks", None)

    changed = before != after
    diff = _render_diff(before, after) if changed else ""

    if dry_run or not changed:
        return HookInstallResult(
            settings_path=settings_path,
            backup_path=None,
            script_path=script_path,
            changed=changed,
            diff=diff,
        )

    # Materialize. Always back up first if the file exists.
    backup_path: Path | None = None
    if settings_path.exists():
        backup_path = _backup(settings_path)
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings_path.write_text(json.dumps(after, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not uninstall:
        _write_hook_script(script_path)

    return HookInstallResult(
        settings_path=settings_path,
        backup_path=backup_path,
        script_path=script_path,
        changed=True,
        diff=diff,
    )


# ────────────────────── Typer command ──────────────────────


def install_hooks_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print diff without writing."),
    uninstall: bool = typer.Option(False, "--uninstall", help="Remove csm hook entries."),
) -> None:
    """Install (or uninstall) csm hooks into ``~/.claude/settings.json``.

    Always backs up the existing settings file with a ``.bak.<timestamp>``
    suffix before writing. Re-running on an already-installed config is a
    no-op.
    """
    result = install_hooks(dry_run=dry_run, uninstall=uninstall)
    if not result.changed:
        typer.echo(f"No changes — {result.settings_path} already up to date.")
        return
    if dry_run:
        typer.echo(f"Dry run — would update {result.settings_path}.")
        typer.echo(result.diff)
        return
    if result.backup_path is not None:
        typer.echo(f"Backed up existing settings to: {result.backup_path}")
    if uninstall:
        typer.echo(f"Uninstalled csm hooks from {result.settings_path}.")
    else:
        typer.echo(f"Installed csm hooks into {result.settings_path}.")
        typer.echo(f"Hook script: {result.script_path}")
