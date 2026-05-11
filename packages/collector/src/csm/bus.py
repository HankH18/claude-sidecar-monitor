"""In-process pub/sub for ingestion → SSE/aggregator wiring.

Producers (hook receiver T6, JSONL watcher T7, hang scanner T8) call
``bus.publish(event)``. Consumers (SSE multiplexer T11, token aggregator
T9) iterate the queue returned by ``bus.subscribe()``.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal[
    "session_update",
    "event",
    "transcript_message",
    "hang",
    "settings_changed",
    # v2 additions
    "subagent_update",        # virtual subagent row created/updated (V2.C2)
    "session_digest_update",  # activity_summary changed (V2.B1)
    "permission_request",     # new pending decision (V2.D2/3)
]


@dataclass
class BusEvent:
    kind: EventKind
    session_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class Bus:
    """Fan-out asyncio queue. One queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[BusEvent]] = []
        self._lock = asyncio.Lock()
        # Captured at server-startup time so publisher threads (the
        # hook receiver running in ``asyncio.to_thread``, the JSONL
        # watcher's own thread, the hang scanner background tick) can
        # do ``asyncio.run_coroutine_threadsafe(bus.publish(...),
        # bus.main_loop)`` without each individually trying to find a
        # loop in their (loopless) worker context. See the v2 review
        # finding about ``asyncio.get_running_loop()`` raising
        # ``RuntimeError`` inside ``to_thread`` workers.
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """Record the asyncio loop publishers should schedule against.

        Call once from a FastAPI lifespan ``startup`` (with
        ``asyncio.get_running_loop()``). Tests that exercise the bus
        from sync helpers can either call this with their own loop or
        leave it None — publishers fall back to ``get_running_loop``
        and degrade silently when neither is available.
        """
        self._main_loop = loop

    @property
    def main_loop(self) -> asyncio.AbstractEventLoop | None:
        """Return the captured loop, or None if it's closed.

        A closed loop is functionally absent — ``run_coroutine_threadsafe``
        against it raises immediately and corrupts ``main_loop`` for
        the next test (pytest-asyncio creates a fresh loop per test in
        ``asyncio_mode=auto``). Returning None lets callers fall back
        to ``get_running_loop`` (which will succeed under the current
        test's loop) or degrade silently.
        """
        loop = self._main_loop
        if loop is None or loop.is_closed():
            return None
        return loop

    async def publish(self, event: BusEvent) -> None:
        # Opportunistically capture the running loop so cross-thread
        # publishers (the hook receiver in to_thread workers, etc.) can
        # target it via run_coroutine_threadsafe without needing the
        # server.py lifespan to wire it up explicitly. Recapture if the
        # previously-captured loop has been closed (pytest creates a
        # fresh loop per test).
        if self._main_loop is None or self._main_loop.is_closed():
            with contextlib.suppress(RuntimeError):
                self._main_loop = asyncio.get_running_loop()
        async with self._lock:
            for queue in list(self._subscribers):
                # Drop the OLDEST queued event when a subscriber's queue
                # is full, then enqueue the new one. This protects the
                # publisher (which may be the receiver thread, the JSONL
                # watcher, the scanner, or the token aggregator emitting
                # back at itself) from back-pressure caused by ANY single
                # slow subscriber — e.g. an SSE client on a phone that's
                # behind a flaky tailnet. Dropped events show up in
                # ``transcript_messages`` / ``sessions`` / ``events`` —
                # the database is the source of truth; SSE is a best-
                # effort live channel. Slow consumers reconnect and
                # /api/state refetches the latest snapshot.
                if queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                queue.put_nowait(event)

    async def subscribe(self, max_buffer: int = 256) -> asyncio.Queue[BusEvent]:
        queue: asyncio.Queue[BusEvent] = asyncio.Queue(maxsize=max_buffer)
        async with self._lock:
            self._subscribers.append(queue)
            # Belt-and-suspenders loop capture: subscribers are always
            # registered from within the asyncio loop (SSE endpoint,
            # test fixture, lifespan startup), so this guarantees the
            # bus knows the loop even if no publish has happened yet.
            if self._main_loop is None or self._main_loop.is_closed():
                with contextlib.suppress(RuntimeError):
                    self._main_loop = asyncio.get_running_loop()
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[BusEvent]) -> None:
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


# Singleton — phases past 3 import this directly.
bus = Bus()
