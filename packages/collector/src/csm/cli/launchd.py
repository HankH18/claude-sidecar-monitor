"""``csm install-launchd`` / ``csm uninstall-launchd``.

Renders the LaunchAgent plist template (bundled in
:mod:`csm.cli._launchd_template`) into ``~/Library/LaunchAgents/`` and
attempts a graceful ``launchctl bootstrap``.

The harness sandbox blocks ``launchctl`` invocations, so the subprocess
call is wrapped in ``try/except`` and the user-runnable command is also
printed for manual execution. This way the code is correct under sandbox
test runs and useful in real deployments.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import typer

from csm.cli._launchd_template import PLIST_TEMPLATE

LAUNCHD_LABEL = "com.hank.claude-sidecar-monitor"


def _user_launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def plist_install_path() -> Path:
    """Where the rendered plist gets written."""
    return _user_launch_agents_dir() / f"{LAUNCHD_LABEL}.plist"


def _resolve_csm_bin() -> str:
    """Best-effort: ``shutil.which`` first, fall back to ``~/.local/bin/csm``.

    ``uv tool install`` puts entrypoints under ``~/.local/bin`` by default,
    so when running from the project venv the ``which`` lookup finds the
    venv's ``csm`` shim while a user installation finds ``~/.local/bin/csm``.
    """
    found = shutil.which("csm")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "csm"
    return str(fallback)


def render_plist(
    *,
    csm_bin: str | None = None,
    user: str | None = None,
    home: Path | None = None,
) -> str:
    """Render the bundled plist template with the substitutions."""
    csm_bin = csm_bin or _resolve_csm_bin()
    user = user or getpass.getuser()
    home_str = str(home if home is not None else Path.home())
    return (
        PLIST_TEMPLATE.replace("__CSM_BIN__", csm_bin)
        .replace("__USER__", user)
        .replace("__HOME__", home_str)
    )


def _bootstrap_command(plist_path: Path) -> list[str]:
    return [
        "launchctl",
        "bootstrap",
        f"gui/{os.getuid()}",
        str(plist_path),
    ]


def _bootout_command(plist_path: Path) -> list[str]:
    return [
        "launchctl",
        "bootout",
        f"gui/{os.getuid()}",
        str(plist_path),
    ]


def _try_run(cmd: list[str]) -> tuple[bool, str]:
    """Run a subprocess and return ``(success, message)``.

    Failures (PermissionError, FileNotFoundError, non-zero exit) are caught
    and reported rather than raised — the harness sandbox blocks
    ``launchctl`` and we want graceful degradation.
    """
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)
    except FileNotFoundError as exc:
        return False, f"{cmd[0]}: not found ({exc})"
    except PermissionError as exc:
        return False, f"{cmd[0]}: permission denied ({exc})"
    except subprocess.SubprocessError as exc:
        return False, f"{cmd[0]}: {exc}"
    if result.returncode == 0:
        return True, result.stdout.strip() or "ok"
    err = (result.stderr or result.stdout).strip()
    return False, f"exit={result.returncode}: {err}"


@dataclass(frozen=True)
class LaunchdInstallResult:
    plist_path: Path
    bootstrap_attempted: bool
    bootstrap_ok: bool
    bootstrap_message: str
    manual_command: str


def install_launchd(
    *,
    plist_path: Path | None = None,
    csm_bin: str | None = None,
    user: str | None = None,
    home: Path | None = None,
    attempt_bootstrap: bool = True,
) -> LaunchdInstallResult:
    """Write the rendered plist and (best-effort) bootstrap it.

    The ``launchctl bootstrap gui/$UID …`` call is wrapped in ``try/except``
    because the harness blocks ``launchctl``. When it fails — or
    ``attempt_bootstrap`` is False — the function still writes the plist and
    returns the manual command for the user to run.
    """
    plist_path = plist_path or plist_install_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_plist(csm_bin=csm_bin, user=user, home=home)
    plist_path.write_text(rendered, encoding="utf-8")
    plist_path.chmod(0o644)

    manual = " ".join(_bootstrap_command(plist_path))

    if not attempt_bootstrap:
        return LaunchdInstallResult(
            plist_path=plist_path,
            bootstrap_attempted=False,
            bootstrap_ok=False,
            bootstrap_message="skipped",
            manual_command=manual,
        )

    ok, msg = _try_run(_bootstrap_command(plist_path))
    return LaunchdInstallResult(
        plist_path=plist_path,
        bootstrap_attempted=True,
        bootstrap_ok=ok,
        bootstrap_message=msg,
        manual_command=manual,
    )


def uninstall_launchd(
    *,
    plist_path: Path | None = None,
    attempt_bootout: bool = True,
) -> tuple[bool, str]:
    """Best-effort ``launchctl bootout`` then remove the plist file.

    Returns ``(removed, bootout_message)``. ``removed`` is True if the plist
    file no longer exists at the end of the call.
    """
    plist_path = plist_path or plist_install_path()
    bootout_msg = "skipped"
    if attempt_bootout and plist_path.exists():
        _, bootout_msg = _try_run(_bootout_command(plist_path))
    if plist_path.exists():
        plist_path.unlink()
    return (not plist_path.exists()), bootout_msg


# ────────────────────── Typer command ──────────────────────


def install_launchd_command(
    no_bootstrap: bool = typer.Option(
        False, "--no-bootstrap", help="Write the plist but don't run launchctl."
    ),
) -> None:
    """Install the LaunchAgent plist into ``~/Library/LaunchAgents/``.

    Attempts ``launchctl bootstrap gui/$UID …`` after writing. If that
    fails (sandbox / launchctl missing / permissions), prints the command
    so the user can run it themselves.
    """
    result = install_launchd(attempt_bootstrap=not no_bootstrap)
    typer.echo(f"Wrote LaunchAgent plist: {result.plist_path}")
    if result.bootstrap_attempted:
        if result.bootstrap_ok:
            typer.echo("launchctl bootstrap: ok")
            return
        typer.echo(f"launchctl bootstrap failed ({result.bootstrap_message}).")
    typer.echo("Run this manually if needed:")
    typer.echo(f"  {result.manual_command}")


def uninstall_launchd_command() -> None:
    """Remove the LaunchAgent plist (after best-effort ``launchctl bootout``)."""
    removed, msg = uninstall_launchd()
    typer.echo(f"launchctl bootout: {msg}")
    if removed:
        typer.echo("LaunchAgent plist removed.")
    else:
        typer.echo("LaunchAgent plist not present.")
