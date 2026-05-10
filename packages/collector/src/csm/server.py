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

from fastapi import FastAPI

from csm import __version__
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

    # Try to load the encryption key from Keychain. If it's missing,
    # we fall back to an unencrypted DB so dev/test boots cleanly.
    # Production ``csm install`` is responsible for setting the key.
    key: bytes | None = None
    try:
        from csm.crypto import get_key_from_keychain

        key = get_key_from_keychain()
    except Exception:
        key = None

    app.state.db = connect(key=key, db_path=paths.db)
    try:
        yield
    finally:
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

    return app


app = create_app()
