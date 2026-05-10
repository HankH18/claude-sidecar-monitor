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
                # Drop on full to avoid back-pressure into the receiver.
                # SSE consumers that fall behind will just miss frames;
                # the database is the source of truth.
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
