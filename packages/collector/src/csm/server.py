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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from csm import __version__
from csm.api import router as api_router
from csm.config import Paths
from csm.db import connect
from csm.hooks import router as hooks_router

# Paths under these prefixes must never fall through to the SPA — they're
# owned by other routers, and a fall-through would mask a real 404 as the
# dashboard shell.
_API_PREFIXES = ("api/", "hook/", "stream", "healthz")
_TOKEN_PLACEHOLDER = "__CSM_TOKEN__"


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

    # V2.D — mark any pending permission requests older than 1h as
    # timed_out at startup. After a process restart the in-memory
    # PendingDecisions registry is empty, so awaiters from the prior
    # process are gone; the rows stay around for audit + dashboard
    # history but shouldn't show up as "pending" any longer.
    from csm.permissions import cleanup_stale_pending

    cleanup_stale_pending(app.state.db)

    # V3.A — re-derive session titles using the current
    # `derive_title_from_user_prompt` heuristic. Idempotent: only writes
    # rows whose stored title actually differs from what we'd produce
    # now, so improvements to the heuristic propagate to historical
    # sessions without an explicit `csm reindex` step.
    from csm.identity import backfill_titles

    backfill_titles(app.state.db)

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


def _resolve_static_dir() -> Path | None:
    bundled = Path(__file__).resolve().parent / "_static"
    if bundled.exists():
        return bundled
    monorepo_dist = Path(__file__).resolve().parent.parent.parent.parent / "dashboard" / "dist"
    return monorepo_dist if monorepo_dist.exists() else None


def _read_api_secret(app: FastAPI) -> str:
    # No caching — settings can change at runtime (regenerate-secret in
    # the dashboard). The cost is one indexed lookup per index.html serve;
    # asset fetches don't hit this path.
    db = getattr(app.state, "db", None)
    if db is None:
        return ""
    row = db.execute("SELECT value FROM settings WHERE key = 'api_secret'").fetchone()
    return str(row[0]) if row and row[0] else ""


def _render_index(app: FastAPI) -> HTMLResponse:
    template: str | None = getattr(app.state, "index_template", None)
    if template is None:
        raise HTTPException(status_code=404, detail="dashboard bundle not built")
    secret = _read_api_secret(app)
    html = template.replace(_TOKEN_PLACEHOLDER, secret)
    # Cache-Control: index.html is the SPA shell — never cache, since it
    # carries the api_secret and updates when the bundle ships.
    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store"},
    )


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

    # Static dashboard — only if the bundle has been built. In dev,
    # `bun run dev` serves the dashboard separately on :5173 and this
    # block is a no-op.
    static_dir = _resolve_static_dir()
    if static_dir is not None:
        index_path = static_dir / "index.html"
        app.state.index_template = (
            index_path.read_text(encoding="utf-8") if index_path.exists() else None
        )

        @app.get("/", include_in_schema=False)
        async def index(request: Request) -> HTMLResponse:
            return _render_index(request.app)

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str, request: Request) -> Response:
            # Defensive: never shadow API/hook/stream/health 404s with
            # the SPA shell. FastAPI's route table already matches
            # explicit routes first, but a typo on /api/foo would
            # otherwise return index.html.
            if full_path.startswith(_API_PREFIXES):
                raise HTTPException(status_code=404)

            # Block directory traversal: any attempt to escape static_dir
            # is treated as a missing asset, never a 200 + sensitive file.
            candidate = (static_dir / full_path).resolve()
            try:
                candidate.relative_to(static_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=404) from None

            if candidate.is_file():
                return FileResponse(candidate)
            return _render_index(request.app)

    return app


app = create_app()
