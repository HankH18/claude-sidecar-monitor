"""``csm`` CLI entry point.

Subcommands are registered here as their phases land. v0.1 starts with
``version`` and ``start``; T13 fills in install/doctor/passphrase/etc.
"""

from __future__ import annotations

import typer

from csm import __version__

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
