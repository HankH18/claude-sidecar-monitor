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

from dataclasses import asdict, dataclass
from typing import Any

__all__ = [
    "DailyRow",
    "ModelTokens",
    "SubtreeTokens",
    "get_daily_totals",
    "get_session_tokens_by_model",
    "get_subtree_tokens",
    "recompute_session_tokens",
]


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
