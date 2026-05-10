"""REST + SSE API surface (T11).

Mounts:
- GET /api/state, /api/sessions/:id, /api/sessions/:id/transcript
- GET /api/tree?worktree=…
- GET /api/tokens, /api/settings
- PATCH /api/settings
- POST /api/test-notification
- GET /stream  (SSE via sse-starlette EventSourceResponse)

All routers depend on a shared DB connection on ``request.app.state.db``
(opened in the FastAPI lifespan). SSE multiplexes the in-process bus.
"""

from __future__ import annotations

from csm.api.router import router

__all__ = ["router"]
