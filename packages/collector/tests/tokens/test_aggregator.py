"""Tests for the token aggregator (T9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from csm.db import connect
from csm.tokens import (
    get_daily_totals,
    get_session_tokens_by_model,
    get_subtree_tokens,
    recompute_session_tokens,
)


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


def _create_session(
    conn,
    sid: str,
    *,
    parent: str | None = None,
    worktree: str = "/tmp/proj",
    started: str = "2026-05-10T00:00:00Z",
) -> None:
    conn.execute(
        """
        INSERT INTO sessions (
            session_id, parent_session_id, worktree_root, cwd,
            last_event_at, started_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (sid, parent, worktree, worktree, started, started),
    )


def _add_message(
    conn,
    sid: str,
    *,
    role: str = "assistant",
    model: str = "claude-opus-4-7",
    input_t: int = 100,
    output_t: int = 200,
    cache_read: int = 50,
    cache_creation: int = 25,
    timestamp: str = "2026-05-10T00:00:00Z",
) -> None:
    conn.execute(
        """
        INSERT INTO transcript_messages (
            session_id, role, timestamp, content_json, model,
            input_tokens, output_tokens,
            cache_creation_input_tokens, cache_read_input_tokens
        ) VALUES (?, ?, ?, '{}', ?, ?, ?, ?, ?)
        """,
        (sid, role, timestamp, model, input_t, output_t, cache_creation, cache_read),
    )


def test_recompute_sums_transcript_into_session(db) -> None:
    _create_session(db, "s1")
    _add_message(db, "s1", input_t=100, output_t=200, cache_read=50, cache_creation=25)
    _add_message(db, "s1", input_t=50, output_t=80, cache_read=10, cache_creation=5)

    totals = recompute_session_tokens(db, "s1")
    assert totals == (150, 280, 60, 30)

    row = db.execute(
        "SELECT input_tokens, output_tokens, cache_read_tokens, "
        "cache_write_tokens, primary_model FROM sessions WHERE session_id=?",
        ("s1",),
    ).fetchone()
    assert row[0:4] == (150, 280, 60, 30)
    assert row[4] == "claude-opus-4-7"


def test_recompute_idempotent(db) -> None:
    _create_session(db, "s1")
    _add_message(db, "s1", input_t=10, output_t=20, cache_read=0, cache_creation=0)
    a = recompute_session_tokens(db, "s1")
    b = recompute_session_tokens(db, "s1")
    assert a == b == (10, 20, 0, 0)


def test_recompute_with_no_messages_returns_zeros(db) -> None:
    _create_session(db, "empty")
    totals = recompute_session_tokens(db, "empty")
    assert totals == (0, 0, 0, 0)


# ────────── subtree rollup ──────────


def test_subtree_rollup_one_parent_three_children(db) -> None:
    """Per spec acceptance criteria: 1 parent + 3 children, mixed models."""
    _create_session(db, "P")
    _create_session(db, "C1", parent="P")
    _create_session(db, "C2", parent="P")
    _create_session(db, "C3", parent="P")

    _add_message(db, "P", input_t=100, output_t=200, cache_read=50, cache_creation=25)
    _add_message(db, "C1", input_t=50, output_t=80, cache_read=20, cache_creation=10)
    _add_message(db, "C2", input_t=30, output_t=60, cache_read=10, cache_creation=5)
    _add_message(db, "C3", input_t=40, output_t=70, cache_read=15, cache_creation=8)

    for sid in ("P", "C1", "C2", "C3"):
        recompute_session_tokens(db, sid)

    rollup = get_subtree_tokens(db, "P")
    assert rollup.input == 220  # 100 + 50 + 30 + 40
    assert rollup.output == 410  # 200 + 80 + 60 + 70
    assert rollup.cache_read == 95  # 50 + 20 + 10 + 15
    assert rollup.cache_write == 48  # 25 + 10 + 5 + 8
    assert rollup.descendant_count == 3


def test_subtree_rollup_for_leaf_returns_self_only(db) -> None:
    _create_session(db, "leaf")
    _add_message(db, "leaf", input_t=10, output_t=20, cache_read=0, cache_creation=0)
    recompute_session_tokens(db, "leaf")

    rollup = get_subtree_tokens(db, "leaf")
    assert rollup.input == 10
    assert rollup.output == 20
    assert rollup.descendant_count == 0


def test_subtree_rollup_deep_chain(db) -> None:
    """Three-deep chain: A → B → C."""
    _create_session(db, "A")
    _create_session(db, "B", parent="A")
    _create_session(db, "C", parent="B")
    for sid in ("A", "B", "C"):
        _add_message(db, sid, input_t=10, output_t=10, cache_read=0, cache_creation=0)
        recompute_session_tokens(db, sid)

    a = get_subtree_tokens(db, "A")
    assert a.descendant_count == 2
    assert a.input == 30
    assert a.output == 30


# ────────── per-model breakdown ──────────


def test_per_model_breakdown(db) -> None:
    _create_session(db, "s1")
    _add_message(db, "s1", model="claude-opus-4-7", input_t=100, output_t=200)
    _add_message(db, "s1", model="claude-opus-4-7", input_t=50, output_t=100)
    _add_message(db, "s1", model="claude-sonnet-4-5", input_t=20, output_t=40)

    breakdown = get_session_tokens_by_model(db, "s1")
    by_model = {m.model: m for m in breakdown}
    assert by_model["claude-opus-4-7"].input == 150
    assert by_model["claude-opus-4-7"].output == 300
    assert by_model["claude-sonnet-4-5"].input == 20
    assert by_model["claude-sonnet-4-5"].output == 40


# ────────── daily totals ──────────


def test_daily_totals_groups_by_date_and_model(db) -> None:
    _create_session(db, "s1")
    _add_message(db, "s1", model="opus", input_t=10, output_t=20, timestamp="2026-05-08T10:00:00Z")
    _add_message(db, "s1", model="opus", input_t=5, output_t=10, timestamp="2026-05-08T11:00:00Z")
    _add_message(db, "s1", model="opus", input_t=30, output_t=60, timestamp="2026-05-09T10:00:00Z")
    _add_message(db, "s1", model="sonnet", input_t=2, output_t=4, timestamp="2026-05-09T11:00:00Z")

    daily = get_daily_totals(db, "2026-05-08T00:00:00Z", "2026-05-10T00:00:00Z")
    by_key = {(d.date, d.model): d for d in daily}
    assert by_key[("2026-05-08", "opus")].input == 15
    assert by_key[("2026-05-08", "opus")].output == 30
    assert by_key[("2026-05-09", "opus")].input == 30
    assert by_key[("2026-05-09", "sonnet")].input == 2
