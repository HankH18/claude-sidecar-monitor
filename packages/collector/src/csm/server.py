"""FastAPI application factory.

Mounts ``/healthz``, ``/hook/<event>`` (T6), and reserves space for
``/api/*`` (T11) and ``/stream`` (T11) which land in their phases.

The application opens a SQLCipher connection at startup using the key
cached in macOS Keychain (T29). For development without a Keychain
entry, the server still boots — the DB just opens unencrypted. CI tests
bypass this entirely and inject their own connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from csm import __version__
from csm.api import router as api_router
from csm.config import Paths
from csm.db import connect
from csm.hooks import router as hooks_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the DB at startup, close on shutdown.

    Phases past 3 (JSONL watcher, hang scanner, etc.) attach more
    background tasks here.
    """
    paths = Paths.from_env()

    # Try to load the encryption key from Keychain. If a pending-rotation
    # entry exists (passphrase rotation died mid-sequence), the crypto
    # module figures out which key actually opens the DB and cleans up.
    # If both are missing, fall back to an unencrypted DB so dev/test boots
    # cleanly. Production ``csm install`` is responsible for the initial key.
    key: bytes | None = None
    try:
        from csm.crypto import recover_from_pending_rotation

        key = recover_from_pending_rotation(paths.db)
    except Exception:
        key = None

    app.state.db = connect(key=key, db_path=paths.db)

    # Background tasks: hang scanner, token aggregator, ntfy dispatcher.
    # All subscribe to the in-process bus; failures logged, not raised.
    from csm.ntfy import NtfyDispatcher
    from csm.scanner import HangScanner
    from csm.tokens import TokenAggregator

    scanner = HangScanner(app.state.db)
    aggregator = TokenAggregator(app.state.db)
    dispatcher = NtfyDispatcher(app.state.db)
    await scanner.start()
    await aggregator.start()
    await dispatcher.start()

    # JSONL watcher (T7): catch up + tail Claude Code transcripts.
    from csm.jsonl import JsonlWatcher

    watcher = JsonlWatcher(app.state.db, paths.projects)
    watcher.start()

    try:
        yield
    finally:
        watcher.stop()
        await dispatcher.stop()
        await aggregator.stop()
        await scanner.stop()
        app.state.db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="claude-sidecar-monitor",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"ok": True, "version": __version__}

    app.include_router(hooks_router)
    app.include_router(api_router)

    # Static dashboard mount — only if the bundle has been built. In dev,
    # `bun run dev` serves the dashboard separately on :5173.
    static_dir = (
        Path(__file__).resolve().parent / "_static"
        if (Path(__file__).resolve().parent / "_static").exists()
        else Path(__file__).resolve().parent.parent.parent.parent / "dashboard" / "dist"
    )
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="dashboard")

    return app


app = create_app()
