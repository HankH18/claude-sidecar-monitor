"""Token aggregator (T9).

Maintains the four denormalized token columns on the ``sessions`` row
by re-summing from ``transcript_messages``. Exposes helpers used by
the API layer (T11):

- ``recompute_session_tokens(conn, session_id)`` — recompute and write.
- ``get_subtree_tokens(conn, session_id)`` — recursive CTE walking
  ``parent_session_id`` edges; returns ``{input, output, cache_read,
  cache_write, descendant_count}``.
- ``get_session_tokens_by_model(conn, session_id)`` — per-model
  breakdown for one session.
- ``get_daily_totals(conn, start_iso, end_iso)`` — per-day per-model
  totals across all sessions, used by the Tokens dashboard chart.

Called by the JSONL processor on every ingested message; the watcher
debounces per-session triggers to ≤1 per 2 s elsewhere. The scheduler
in this module simply does the work it's asked to do.

NB: ``cache_read_tokens`` denormalised on ``sessions`` corresponds to
the ``cache_read_input_tokens`` field in the JSONL; same for write.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from csm.bus import BusEvent, bus

log = logging.getLogger(__name__)

__all__ = [
    "DailyRow",
    "ModelTokens",
    "SubtreeTokens",
    "TokenAggregator",
    "get_daily_totals",
    "get_session_tokens_by_model",
    "get_subtree_tokens",
    "recompute_session_tokens",
]

# Per docs/spec.md §4.3: aggregator triggers debounced to ≤1 per 2 s
# per session.
DEBOUNCE_SECONDS = 2.0


@dataclass(frozen=True)
class SubtreeTokens:
    input: int
    output: int
    cache_read: int
    cache_write: int
    descendant_count: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ModelTokens:
    model: str
    input: int
    output: int
    cache_read: int
    cache_write: int


@dataclass(frozen=True)
class DailyRow:
    date: str
    model: str
    input: int
    output: int
    cache_read: int
    cache_write: int


def recompute_session_tokens(conn: Any, session_id: str) -> tuple[int, int, int, int]:
    """Re-sum a session's tokens from transcript_messages and write back.

    Returns ``(input, output, cache_read, cache_write)``.
    """
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0),
            COALESCE(SUM(cache_read_input_tokens), 0),
            COALESCE(SUM(cache_creation_input_tokens), 0)
        FROM transcript_messages
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    totals = (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
    conn.execute(
        """
        UPDATE sessions
        SET input_tokens       = ?,
            output_tokens      = ?,
            cache_read_tokens  = ?,
            cache_write_tokens = ?,
            primary_model      = COALESCE(primary_model, (
                SELECT model FROM transcript_messages
                WHERE session_id = ? AND model IS NOT NULL
                ORDER BY message_id DESC LIMIT 1
            ))
        WHERE session_id = ?
        """,
        (*totals, session_id, session_id),
    )
    return totals


def get_subtree_tokens(conn: Any, session_id: str) -> SubtreeTokens:
    """Walk parent → children, return summed token totals for the subtree.

    The session itself is included; ``descendant_count`` counts only
    descendants (not the root).
    """
    row = conn.execute(
        """
        WITH RECURSIVE subtree(session_id, depth) AS (
            SELECT session_id, 0 FROM sessions WHERE session_id = ?
            UNION ALL
            SELECT s.session_id, st.depth + 1
            FROM sessions s
            JOIN subtree st ON s.parent_session_id = st.session_id
        )
        SELECT
            COALESCE(SUM(s.input_tokens), 0),
            COALESCE(SUM(s.output_tokens), 0),
            COALESCE(SUM(s.cache_read_tokens), 0),
            COALESCE(SUM(s.cache_write_tokens), 0),
            (SELECT COUNT(*) - 1 FROM subtree)
        FROM sessions s
        WHERE s.session_id IN (SELECT session_id FROM subtree)
        """,
        (session_id,),
    ).fetchone()
    return SubtreeTokens(
        input=int(row[0]),
        output=int(row[1]),
        cache_read=int(row[2]),
        cache_write=int(row[3]),
        descendant_count=int(row[4]),
    )


def get_session_tokens_by_model(conn: Any, session_id: str) -> list[ModelTokens]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(model, 'unknown'),
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0),
            COALESCE(SUM(cache_read_input_tokens), 0),
            COALESCE(SUM(cache_creation_input_tokens), 0)
        FROM transcript_messages
        WHERE session_id = ?
        GROUP BY model
        ORDER BY (SUM(input_tokens) + SUM(output_tokens)) DESC
        """,
        (session_id,),
    ).fetchall()
    return [
        ModelTokens(
            model=str(model),
            input=int(input_),
            output=int(output),
            cache_read=int(cr),
            cache_write=int(cw),
        )
        for model, input_, output, cr, cw in rows
    ]


def get_daily_totals(conn: Any, start_iso: str, end_iso: str) -> list[DailyRow]:
    """Per-day per-model totals across all sessions.

    ``timestamp`` on transcript_messages is ISO 8601 UTC; we slice the
    first 10 chars to bucket by date.
    """
    rows = conn.execute(
        """
        SELECT
            substr(timestamp, 1, 10) AS date,
            COALESCE(model, 'unknown') AS model,
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0),
            COALESCE(SUM(cache_read_input_tokens), 0),
            COALESCE(SUM(cache_creation_input_tokens), 0)
        FROM transcript_messages
        WHERE timestamp >= ? AND timestamp <= ?
        GROUP BY date, model
        ORDER BY date, model
        """,
        (start_iso, end_iso),
    ).fetchall()
    return [
        DailyRow(
            date=str(date),
            model=str(model),
            input=int(input_),
            output=int(output),
            cache_read=int(cr),
            cache_write=int(cw),
        )
        for date, model, input_, output, cr, cw in rows
    ]


class TokenAggregator:
    """Subscribes to bus ``transcript_message`` events, recomputes per-session
    token totals, and re-publishes a ``session_update`` so SSE clients see the
    new numbers.

    Per docs/spec.md §4.3 / T9: triggers are debounced to ≤1 recompute per
    2 s per session. The aggregator also fires a recompute on
    ``session_update`` events that carry a ``state`` transition into
    ``done`` so the final totals are flushed before the session row goes
    quiet.
    """

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self._task: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[BusEvent] | None = None
        self._last_run: dict[str, float] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        # Subscribe synchronously so callers that publish immediately
        # after ``start()`` returns are guaranteed to land in our queue.
        self._queue = await bus.subscribe()
        self._task = asyncio.create_task(self._run(), name="csm-token-aggregator")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        if self._queue is not None:
            await bus.unsubscribe(self._queue)
            self._queue = None

    async def _run(self) -> None:
        assert self._queue is not None
        queue = self._queue
        while True:
            event = await queue.get()
            if not self._should_handle(event):
                continue
            sid = event.session_id
            assert sid is not None
            if not self._debounce_ok(sid, event.kind):
                continue
            await asyncio.to_thread(self._recompute_and_emit, sid)

    def _should_handle(self, event: BusEvent) -> bool:
        if event.session_id is None:
            return False
        return event.kind == "transcript_message" or (
            event.kind == "session_update" and event.data.get("state") == "done"
        )

    def _debounce_ok(self, session_id: str, kind: str) -> bool:
        # Always recompute on the 'done' transition so final totals are flushed.
        if kind == "session_update":
            return True
        now = time.monotonic()
        last = self._last_run.get(session_id, 0.0)
        if now - last < DEBOUNCE_SECONDS:
            return False
        self._last_run[session_id] = now
        return True

    def _recompute_and_emit(self, session_id: str) -> None:
        try:
            totals = recompute_session_tokens(self.conn, session_id)
        except Exception:
            log.exception("token aggregator: recompute failed for %s", session_id)
            return
        # Re-publish so SSE pushes the freshly aggregated numbers to the UI.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.run_coroutine_threadsafe(
            bus.publish(
                BusEvent(
                    kind="session_update",
                    session_id=session_id,
                    data={
                        "session_id": session_id,
                        "input_tokens": totals[0],
                        "output_tokens": totals[1],
                        "cache_read_tokens": totals[2],
                        "cache_write_tokens": totals[3],
                        "source": "token_aggregator",
                    },
                )
            ),
            loop,
        )
