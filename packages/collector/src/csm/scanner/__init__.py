"""Hang scanner (T8).

A 5-second asyncio loop launched from the FastAPI lifespan. On each
tick, sessions in ``running`` or ``tool`` state whose last event is
older than the red threshold transition to ``hung`` and emit a
``hang`` BusEvent (consumed by T11 SSE and T12 ntfy dispatcher).

The ``PreCompact`` extension (per docs/spec.md §4.1): when a session's
last_event_name is ``PreCompact``, both yellow and red thresholds are
extended by 60 s so the long compaction pause doesn't false-flag.

The scanner doesn't *un-hang* — when a new event arrives at the
receiver (T6) it transitions the session back out of ``hung`` itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from csm.bus import BusEvent, bus

log = logging.getLogger(__name__)

DEFAULT_TICK_SECONDS = 5.0
PRECOMPACT_EXTENSION_MS = 60_000


@dataclass(frozen=True)
class HangThresholds:
    yellow_ms: int
    red_ms: int


def load_thresholds(conn: Any) -> HangThresholds:
    rows = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    return HangThresholds(
        yellow_ms=int(rows.get("hang_yellow_ms", "60000")),
        red_ms=int(rows.get("hang_red_ms", "180000")),
    )


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def scan_once(conn: Any, *, now: datetime | None = None) -> list[str]:
    """One pass of the hang scanner. Returns the IDs that transitioned.

    Pure-sync; safe to call from a thread or the event loop. For each
    transition we emit a ``hang`` BusEvent. The bus is asyncio-based;
    if there's no running loop we degrade silently (test path).
    """
    now = now or datetime.now(tz=UTC)
    thresholds = load_thresholds(conn)
    candidates = conn.execute(
        """
        SELECT session_id, state, last_event_at, last_event_name,
               worktree_root, parent_session_id
        FROM sessions
        WHERE state IN ('running', 'tool')
        """
    ).fetchall()

    transitioned: list[str] = []
    for sid, _state, last_at, last_event, worktree, parent in candidates:
        try:
            elapsed_ms = int((now - _parse_iso(last_at)).total_seconds() * 1000)
        except (ValueError, TypeError):
            log.warning("scanner: unparseable last_event_at for %s: %r", sid, last_at)
            continue

        red = thresholds.red_ms
        if last_event == "PreCompact":
            red += PRECOMPACT_EXTENSION_MS

        if elapsed_ms <= red:
            continue

        # Compare-and-swap on ``last_event_at`` to avoid racing the receiver.
        # If a new hook event landed for this session between our SELECT and
        # our UPDATE, ``last_event_at`` will have moved and the WHERE clause
        # won't match — the UPDATE no-ops and rowcount==0 tells us to skip
        # the hang emission. SQLite's per-statement atomicity guarantees the
        # WHERE matches against the row's current (post-receiver) state.
        cursor = conn.execute(
            "UPDATE sessions SET state = 'hung' "
            "WHERE session_id = ? "
            "AND state IN ('running', 'tool') "
            "AND last_event_at = ?",
            (sid, last_at),
        )
        if cursor.rowcount == 0:
            # Receiver wrote a new event for this session between our
            # SELECT and our UPDATE — skip the transition. Next scan tick
            # will re-evaluate against the fresh last_event_at.
            continue
        transitioned.append(sid)
        _emit(
            BusEvent(
                kind="hang",
                session_id=sid,
                data={
                    "session_id": sid,
                    "elapsed_ms": elapsed_ms,
                    "red_threshold_ms": red,
                    "last_event_name": last_event,
                    "worktree_root": worktree,
                    "parent_session_id": parent,
                    "is_top_level": parent is None,
                },
            )
        )
    return transitioned


def _emit(event: BusEvent) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.run_coroutine_threadsafe(bus.publish(event), loop)


class HangScanner:
    """Owns the asyncio task that ticks ``scan_once``."""

    def __init__(self, conn: Any, *, tick_seconds: float = DEFAULT_TICK_SECONDS) -> None:
        self.conn = conn
        self.tick_seconds = tick_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="csm-hang-scanner")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(scan_once, self.conn)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("hang scanner tick failed")
            await asyncio.sleep(self.tick_seconds)
