"""ntfy.sh dispatcher (T12).

Subscribes to ``csm.bus`` and POSTs notifications to ``ntfy.sh/<topic>``
on hang / top-level done / waiting_user events. No-op if the configured
``ntfy_topic`` is empty.

Triggers (per docs/spec.md §7 / T12):
- ``hang``         priority 5  '🟥 [{project}] hung for {Xm} on {tool}'
- ``done`` (top)   priority 3  '✅ [{project}] complete (took Xm, N tools)'
- ``waiting_user`` priority 4  '🔔 [{project}] needs permission'

Top-level vs subagent: only sessions with no ``parent_session_id`` emit
"complete" — otherwise every Task subagent finishing would push.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import httpx

from csm.bus import BusEvent, bus
from csm.config import Paths

log = logging.getLogger(__name__)

NTFY_BASE = "https://ntfy.sh"


def _format_elapsed(ms: int) -> str:
    if ms < 60_000:
        return f"{ms // 1000}s"
    if ms < 3_600_000:
        return f"{ms // 60_000}m"
    h, rem = divmod(ms, 3_600_000)
    return f"{h}h{rem // 60_000}m"


def _build_payload(event: BusEvent, *, project: str, topic: str) -> dict[str, Any] | None:
    """Return an httpx kwargs dict to POST, or ``None`` if we shouldn't push."""
    data = event.data
    if event.kind == "hang":
        elapsed = _format_elapsed(int(data.get("elapsed_ms", 0)))
        last_tool = data.get("last_tool_name") or data.get("last_event_name") or "—"
        title = f"[{project}] hung for {elapsed}+"
        body = f"on tool: {last_tool}"
        priority = 5
        tags = ["warning", "hourglass"]
    elif event.kind == "session_update":
        state = data.get("state")
        if state == "done" and not data.get("parent_session_id"):
            title = f"[{project}] complete"
            body = "session done"
            priority = 3
            tags = ["white_check_mark"]
        elif state == "waiting_user":
            title = f"[{project}] needs permission"
            body = str(data.get("last_tool_name") or "permission request")
            priority = 4
            tags = ["bell"]
        else:
            return None
    else:
        return None

    return {
        "url": f"{NTFY_BASE}/{topic}",
        "content": body,
        "headers": {
            "Title": title,
            "Priority": str(priority),
            "Tags": ",".join(tags),
        },
    }


def _project_label_for(event: BusEvent) -> str:
    worktree = event.data.get("worktree_root") or ""
    if not worktree:
        return "csm"
    return worktree.rstrip("/").split("/")[-1] or "csm"


def _topic_for(conn: Any) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key='ntfy_topic'").fetchone()
    return row[0] if row else ""


async def _post(client: httpx.AsyncClient, payload: dict[str, Any]) -> bool:
    try:
        resp = await client.post(
            payload["url"],
            content=payload["content"],
            headers=payload["headers"],
            timeout=5.0,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.warning("ntfy: POST failed: %s", exc)
        return False


async def send_test_notification(topic: str) -> bool:
    """Fire a sample push to verify the configured topic. Used by
    ``POST /api/test-notification`` and the Settings page."""
    if not topic:
        return False
    async with httpx.AsyncClient() as client:
        return await _post(
            client,
            {
                "url": f"{NTFY_BASE}/{topic}",
                "content": "If you see this, your topic is wired up.",
                "headers": {
                    "Title": "csm test",
                    "Priority": "3",
                    "Tags": "white_check_mark",
                },
            },
        )


class NtfyDispatcher:
    """Subscribes to ``csm.bus`` and dispatches matching events to ntfy.

    Lifecycle managed by the FastAPI lifespan: ``await dispatcher.start()``
    on startup, ``await dispatcher.stop()`` on shutdown.

    Topic is read from the DB on every dispatch so settings updates take
    effect without restart.
    """

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self._task: asyncio.Task[None] | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._client = httpx.AsyncClient()
        self._task = asyncio.create_task(self._run(), name="csm-ntfy")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _run(self) -> None:
        queue = await bus.subscribe()
        try:
            while True:
                event = await queue.get()
                # Fire-and-forget so a slow ntfy.sh (5-second per-POST
                # timeout) doesn't block the bus drain. If we awaited
                # _dispatch directly, a single slow upstream could fill
                # our queue (256-deep) and trigger bus drop-on-full for
                # OTHER subscribers, not just for our notifications. The
                # task is created with a stable name so a log filter
                # `csm-ntfy-fire-*` can isolate stuck pushes.
                fire = asyncio.create_task(
                    self._dispatch(event),
                    name=f"csm-ntfy-fire-{event.kind}-{event.session_id or '_'}",
                )
                # Don't await fire — drop the reference and let the loop
                # take it. We attach a done callback that surfaces
                # exceptions in the log so silent failures don't pile up.
                fire.add_done_callback(_log_fire_exceptions)
        finally:
            await bus.unsubscribe(queue)

    async def _dispatch(self, event: BusEvent) -> None:
        if event.kind not in {"hang", "session_update"}:
            return
        topic = await asyncio.to_thread(_topic_for, self.conn)
        if not topic:
            return
        payload = _build_payload(event, project=_project_label_for(event), topic=topic)
        if payload is None:
            return
        assert self._client is not None
        await _post(self._client, payload)


def _log_fire_exceptions(task: asyncio.Task[None]) -> None:
    """Done-callback for fire-and-forget dispatch tasks. Swallows
    CancelledError; logs any other exception. We never raise here —
    that would propagate into the event loop and crash it."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.warning("ntfy: dispatch task '%s' raised: %r", task.get_name(), exc)


# Make Paths importable here so callers don't have to.
__all__ = [
    "NTFY_BASE",
    "NtfyDispatcher",
    "Paths",
    "send_test_notification",
]
