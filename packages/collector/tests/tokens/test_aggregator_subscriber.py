"""Tests for the asyncio TokenAggregator that subscribes to the bus."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from csm.bus import BusEvent, bus
from csm.db import connect
from csm.tokens import TokenAggregator


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


async def _wait_for_totals(db, sid: str, expected_input: int, timeout: float = 1.5) -> bool:
    """Poll until the session row reflects the expected token total."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        row = db.execute(
            "SELECT input_tokens FROM sessions WHERE session_id=?", (sid,)
        ).fetchone()
        if row and row[0] == expected_input:
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_aggregator_recomputes_on_transcript_message(db) -> None:
    """Bus publishes a transcript_message → aggregator recomputes the row."""
    sid = "agg-test-1"
    db.execute(
        """
        INSERT INTO sessions (session_id, worktree_root, cwd, last_event_at, started_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (sid, "/tmp/x", "/tmp/x", "2026-05-10T00:00:00Z", "2026-05-10T00:00:00Z"),
    )
    db.execute(
        """
        INSERT INTO transcript_messages
            (session_id, role, timestamp, content_json, model,
             input_tokens, output_tokens,
             cache_creation_input_tokens, cache_read_input_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, "assistant", "2026-05-10T00:00:00Z", "{}", "opus", 42, 84, 0, 0),
    )

    agg = TokenAggregator(db)
    await agg.start()
    try:
        await bus.publish(BusEvent(kind="transcript_message", session_id=sid, data={}))
        assert await _wait_for_totals(db, sid, 42)
    finally:
        await agg.stop()


@pytest.mark.asyncio
async def test_aggregator_debounces_within_window(db) -> None:
    """Two messages arrive within DEBOUNCE_SECONDS → at most one recompute."""
    sid = "agg-test-2"
    db.execute(
        """
        INSERT INTO sessions (session_id, worktree_root, cwd, last_event_at, started_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (sid, "/tmp/x", "/tmp/x", "2026-05-10T00:00:00Z", "2026-05-10T00:00:00Z"),
    )
    db.execute(
        """
        INSERT INTO transcript_messages
            (session_id, role, timestamp, content_json, model,
             input_tokens, output_tokens,
             cache_creation_input_tokens, cache_read_input_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, "assistant", "2026-05-10T00:00:00Z", "{}", "opus", 10, 20, 0, 0),
    )

    agg = TokenAggregator(db)
    await agg.start()
    try:
        # First publish triggers a recompute.
        await bus.publish(BusEvent(kind="transcript_message", session_id=sid, data={}))
        assert await _wait_for_totals(db, sid, 10)

        # Append more usage and re-publish immediately. Debounce should
        # SKIP the second recompute, leaving the row at 10/20.
        db.execute(
            """
            INSERT INTO transcript_messages
                (session_id, role, timestamp, content_json, model,
                 input_tokens, output_tokens,
                 cache_creation_input_tokens, cache_read_input_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sid, "assistant", "2026-05-10T00:00:01Z", "{}", "opus", 5, 15, 0, 0),
        )
        await bus.publish(BusEvent(kind="transcript_message", session_id=sid, data={}))
        await asyncio.sleep(0.2)  # let any recompute finish
        row = db.execute(
            "SELECT input_tokens FROM sessions WHERE session_id=?", (sid,)
        ).fetchone()
        assert row[0] == 10  # debounced; not 15
    finally:
        await agg.stop()


@pytest.mark.asyncio
async def test_aggregator_recomputes_on_done_transition(db) -> None:
    """A 'done' session_update bypasses debounce so final totals flush."""
    sid = "agg-test-3"
    db.execute(
        """
        INSERT INTO sessions (session_id, worktree_root, cwd, last_event_at, started_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (sid, "/tmp/x", "/tmp/x", "2026-05-10T00:00:00Z", "2026-05-10T00:00:00Z"),
    )
    db.execute(
        """
        INSERT INTO transcript_messages
            (session_id, role, timestamp, content_json, model,
             input_tokens, output_tokens,
             cache_creation_input_tokens, cache_read_input_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, "assistant", "2026-05-10T00:00:00Z", "{}", "opus", 99, 1, 0, 0),
    )

    agg = TokenAggregator(db)
    await agg.start()
    try:
        await bus.publish(
            BusEvent(
                kind="session_update",
                session_id=sid,
                data={"state": "done"},
            )
        )
        assert await _wait_for_totals(db, sid, 99)
    finally:
        await agg.stop()


@pytest.mark.asyncio
async def test_aggregator_ignores_unrelated_events(db) -> None:
    """Hang events and other kinds shouldn't trigger recomputes."""
    sid = "agg-test-4"
    db.execute(
        """
        INSERT INTO sessions (session_id, worktree_root, cwd, last_event_at, started_at,
                              input_tokens, output_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, "/tmp/x", "/tmp/x", "2026-05-10T00:00:00Z", "2026-05-10T00:00:00Z", 7, 7),
    )

    agg = TokenAggregator(db)
    await agg.start()
    try:
        await bus.publish(BusEvent(kind="hang", session_id=sid, data={}))
        await asyncio.sleep(0.15)
        # No transcript_messages, but if recompute fired it would zero out
        # the existing tokens. Stale row should remain at 7/7.
        row = db.execute(
            "SELECT input_tokens, output_tokens FROM sessions WHERE session_id=?", (sid,)
        ).fetchone()
        assert row == (7, 7)
    finally:
        await agg.stop()
