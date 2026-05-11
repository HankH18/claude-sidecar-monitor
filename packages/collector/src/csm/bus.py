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

    async def publish(self, event: BusEvent) -> None:
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
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[BusEvent]) -> None:
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


# Singleton — phases past 3 import this directly.
bus = Bus()
