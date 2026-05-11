"""HTTP route definitions."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from csm.api.models import (
    ModelTokens,
    SessionDetail,
    Settings,
    SettingsPatch,
    StateSnapshot,
    TokensResponse,
    TranscriptPage,
    TreeNode,
)
from csm.api.permissions import router as _permissions_router
from csm.api.queries import (
    daily_totals,
    get_session,
    get_settings_dict,
    latest_event_at,
    list_sessions,
    list_transcript,
    project_tree,
    top_projects,
    top_sessions,
    totals_by_model,
)
from csm.bus import bus
from csm.tokens import get_session_tokens_by_model

router = APIRouter()
# V2.D — phone permission approval endpoints. Mounted on the same prefix
# (/api/permission-requests). Auth via require_bearer on each route.
router.include_router(_permissions_router)


def _db(request: Request) -> Any:
    return request.app.state.db


# ────────────────────── /api/state ──────────────────────


@router.get("/api/state", response_model=StateSnapshot)
async def get_state(request: Request) -> StateSnapshot:
    db = _db(request)
    sessions = await asyncio.to_thread(list_sessions, db)
    settings = await asyncio.to_thread(get_settings_dict, db)
    last_evt = await asyncio.to_thread(latest_event_at, db)
    return StateSnapshot(
        sessions=sessions,
        settings=settings,
        last_event_at=last_evt,
    )


# ────────────────────── /api/sessions ──────────────────────


@router.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def get_session_detail(session_id: str, request: Request) -> SessionDetail:
    db = _db(request)
    session = await asyncio.to_thread(get_session, db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "session_not_found", "message": session_id}},
        )
    by_model = await asyncio.to_thread(get_session_tokens_by_model, db, session_id)
    return SessionDetail(
        **session.model_dump(),
        by_model=[
            ModelTokens(
                model=m.model,
                input=m.input,
                output=m.output,
                cache_read=m.cache_read,
                cache_write=m.cache_write,
            )
            for m in by_model
        ],
    )


@router.get(
    "/api/sessions/{session_id}/transcript",
    response_model=TranscriptPage,
)
async def get_transcript(
    session_id: str,
    request: Request,
    cursor: int | None = Query(None, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> TranscriptPage:
    db = _db(request)
    # Query limit+1 to detect whether more rows exist BEYOND this page
    # without needing the client to round-trip an empty next-page request.
    # If we get back limit+1 rows we know there's more; trim and emit a
    # cursor. If we get back ≤limit rows, this was the tail.
    rows = await asyncio.to_thread(
        list_transcript, db, session_id, after=cursor, limit=limit + 1
    )
    if len(rows) > limit:
        messages = rows[:limit]
        next_cursor: int | None = messages[-1].message_id
    else:
        messages = rows
        next_cursor = None
    return TranscriptPage(messages=messages, next_cursor=next_cursor)


# ────────────────────── /api/tree ──────────────────────


@router.get("/api/tree", response_model=list[TreeNode])
async def get_tree(request: Request, worktree: str = Query(..., min_length=1)) -> list[TreeNode]:
    db = _db(request)
    return await asyncio.to_thread(project_tree, db, worktree)


# ────────────────────── /api/tokens ──────────────────────


@router.get("/api/tokens", response_model=TokensResponse)
async def get_tokens(
    request: Request,
    top_sessions_hours: int = Query(
        24,
        ge=1,
        le=24 * 30,
        description="Window for 'top sessions' (hours back from now).",
    ),
    daily_days: int = Query(
        14,
        ge=1,
        le=90,
        description="Window for the daily-totals chart (days back from now).",
    ),
) -> TokensResponse:
    db = _db(request)
    now = datetime.now(tz=UTC)
    since = (now - timedelta(hours=top_sessions_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    daily_start = (now - timedelta(days=daily_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    daily_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    return TokensResponse(
        topSessions=await asyncio.to_thread(top_sessions, db, since=since),
        topProjects=await asyncio.to_thread(top_projects, db),
        totalsByModel=await asyncio.to_thread(totals_by_model, db),
        dailyTotals=await asyncio.to_thread(daily_totals, db, daily_start, daily_end),
    )


# ────────────────────── /api/settings ──────────────────────


@router.get("/api/settings", response_model=Settings)
async def get_settings(request: Request) -> Settings:
    db = _db(request)
    raw = await asyncio.to_thread(get_settings_dict, db)
    return Settings(
        hang_yellow_ms=int(raw.get("hang_yellow_ms", "60000")),
        hang_red_ms=int(raw.get("hang_red_ms", "180000")),
        ntfy_topic=raw.get("ntfy_topic", ""),
    )


@router.patch("/api/settings", response_model=Settings)
async def patch_settings(patch: SettingsPatch, request: Request) -> Settings:
    db = _db(request)

    def _apply() -> dict[str, str]:
        if patch.hang_yellow_ms is not None:
            db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                ("hang_yellow_ms", str(patch.hang_yellow_ms)),
            )
        if patch.hang_red_ms is not None:
            db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                ("hang_red_ms", str(patch.hang_red_ms)),
            )
        if patch.ntfy_topic is not None:
            db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                ("ntfy_topic", patch.ntfy_topic),
            )
        return get_settings_dict(db)

    raw = await asyncio.to_thread(_apply)
    response = Settings(
        hang_yellow_ms=int(raw.get("hang_yellow_ms", "60000")),
        hang_red_ms=int(raw.get("hang_red_ms", "180000")),
        ntfy_topic=raw.get("ntfy_topic", ""),
    )
    # Notify SSE subscribers so the dashboard's useSettings hook can pick up
    # the new thresholds without a manual reload. Per docs/spec.md §7 SSE
    # event kinds.
    from csm.bus import BusEvent

    await bus.publish(
        BusEvent(kind="settings_changed", session_id=None, data=response.model_dump())
    )
    return response


# ────────────────────── /api/test-notification ──────────────────────


@router.post("/api/test-notification")
async def test_notification(request: Request) -> dict[str, object]:
    """Send a test ntfy push using the configured topic.

    Imports the dispatcher lazily to avoid a circular import at module
    load time (ntfy module also subscribes to bus events).
    """
    from csm.ntfy import send_test_notification

    db = _db(request)
    raw = await asyncio.to_thread(get_settings_dict, db)
    topic = raw.get("ntfy_topic", "")
    delivered = await send_test_notification(topic)
    return {"delivered": delivered, "topic": topic}


# ────────────────────── /stream ──────────────────────


@router.get("/stream")
async def stream(request: Request) -> EventSourceResponse:
    queue = await bus.subscribe()

    async def generator() -> AsyncIterator[dict[str, Any]]:
        # Race queue.get() against a disconnect watcher so a closed client
        # is noticed quickly, not only when the next bus event or 15-s
        # heartbeat arrives. Without this, a phone tab closing during a
        # quiet period holds a 256-event queue + lock contention for up
        # to 15 s — non-fatal but multiplies across reopened tabs.
        disconnect_event = asyncio.Event()

        async def _watch_disconnect() -> None:
            try:
                while not disconnect_event.is_set():
                    if await request.is_disconnected():
                        disconnect_event.set()
                        return
                    # 250 ms cadence is well under the 15 s heartbeat and
                    # under any reasonable user-perception threshold while
                    # being light on the event loop.
                    await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                raise

        watcher = asyncio.create_task(_watch_disconnect(), name="csm-sse-disconnect")
        try:
            while not disconnect_event.is_set():
                get_task = asyncio.create_task(queue.get())
                wait_task = asyncio.create_task(disconnect_event.wait())
                try:
                    done, _pending = await asyncio.wait(
                        {get_task, wait_task},
                        timeout=15.0,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    # Whatever didn't finish: cancel + drain.
                    for t in (get_task, wait_task):
                        if not t.done():
                            t.cancel()
                            with contextlib.suppress(
                                asyncio.CancelledError, BaseException
                            ):
                                await t
                if disconnect_event.is_set():
                    break
                if get_task in done:
                    event = get_task.result()
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {
                                "kind": event.kind,
                                "session_id": event.session_id,
                                "data": event.data,
                            }
                        ),
                    }
                else:
                    # 15-s heartbeat — keeps Tailscale Serve / iOS proxy
                    # paths warm in the absence of bus traffic.
                    yield {"event": "ping", "data": "{}"}
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            await bus.unsubscribe(queue)

    return EventSourceResponse(generator())
