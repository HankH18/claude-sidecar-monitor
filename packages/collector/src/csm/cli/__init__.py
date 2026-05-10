"""``csm`` CLI entry point.

Subcommands are registered here as their phases land. v0.1 ships:

- ``version`` — print package version
- ``start`` — run the collector in the foreground
- ``install`` / ``uninstall`` — first-run bootstrap + reverse
- ``install-hooks`` / ``hooks`` — merge into ``~/.claude/settings.json``
- ``install-launchd`` / ``uninstall-launchd`` — LaunchAgent plist install
- ``doctor`` — diagnostics
- ``change-passphrase`` — atomic passphrase rotation
- ``purge`` — retention pruning + reset
"""

from __future__ import annotations

import typer

from csm import __version__
from csm.cli.doctor import doctor_command
from csm.cli.hooks import install_hooks_command
from csm.cli.install import install_command, uninstall_command
from csm.cli.launchd import install_launchd_command, uninstall_launchd_command
from csm.cli.passphrase import change_passphrase_command
from csm.cli.purge import purge_command

app = typer.Typer(
    name="csm",
    help="claude-sidecar-monitor — observability for Claude Code sessions.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print csm version."""
    typer.echo(f"csm v{__version__}")


@app.command()
def start(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8765, "--port", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable autoreload."),
) -> None:
    """Run the collector in the foreground (development)."""
    import uvicorn

    uvicorn.run(
        "csm.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ────────────────────── lifecycle ──────────────────────

app.command(name="install")(install_command)
app.command(name="uninstall")(uninstall_command)

# ────────────────────── hooks ──────────────────────

app.command(name="install-hooks")(install_hooks_command)
# Alias so `csm hooks --dry-run` works (per scope item #8).
app.command(name="hooks")(install_hooks_command)

# ────────────────────── launchd ──────────────────────

app.command(name="install-launchd")(install_launchd_command)
app.command(name="uninstall-launchd")(uninstall_launchd_command)

# ────────────────────── ops ──────────────────────

app.command(name="doctor")(doctor_command)
app.command(name="change-passphrase")(change_passphrase_command)
app.command(name="purge")(purge_command)
