"""FastAPI application factory.

For now this exposes ``/healthz`` only. Routers for hooks, JSONL, API,
and SSE are mounted in their respective phases.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from csm import __version__


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan.

    Background tasks (JSONL watcher, hang scanner) attach themselves
    here when their phases land. v0.1 starts a no-op lifespan.
    """
    # Phase 3+: start watcher, scanner, etc.
    yield
    # Phase 3+: graceful shutdown


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

    return app


app = create_app()
