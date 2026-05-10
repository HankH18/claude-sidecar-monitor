"""Tests for the agent tree builder (T10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from csm.db import connect
from csm.tree import build_project_tree, resolve_parent


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


WORKTREE = "/tmp/myproj"


def _create_session(
    conn,
    sid: str,
    *,
    started: datetime,
    worktree: str = WORKTREE,
    parent: str | None = None,
) -> None:
    iso = started.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO sessions (
            session_id, parent_session_id, worktree_root, cwd,
            last_event_at, started_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (sid, parent, worktree, worktree, iso, iso),
    )


def _record_task_call(
    conn,
    parent_sid: str,
    when: datetime,
    *,
    tool_use_id: str = "tu_task_1",
) -> None:
    iso = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO events (
            session_id, event_name, received_at,
            tool_name, tool_use_id, payload_json
        ) VALUES (?, 'PreToolUse', ?, 'Task', ?, '{}')
        """,
        (parent_sid, iso, tool_use_id),
    )


def test_resolve_parent_matches_within_window(db) -> None:
    """Coordinator dispatches a Task → child session starts within 30s."""
    coordinator_start = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
    task_call = coordinator_start + timedelta(seconds=10)
    child_start = coordinator_start + timedelta(seconds=15)

    _create_session(db, "coordinator", started=coordinator_start)
    _record_task_call(db, "coordinator", task_call)
    _create_session(db, "child", started=child_start)

    parent = resolve_parent(db, "child")
    assert parent == "coordinator"

    persisted = db.execute(
        "SELECT parent_session_id FROM sessions WHERE session_id='child'"
    ).fetchone()[0]
    assert persisted == "coordinator"


def test_resolve_parent_falls_back_to_none_outside_window(db) -> None:
    """Task call > 30s before the child started → no match."""
    coordinator_start = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
    task_call = coordinator_start + timedelta(seconds=10)
    child_start = coordinator_start + timedelta(seconds=120)  # >> 30s

    _create_session(db, "coordinator", started=coordinator_start)
    _record_task_call(db, "coordinator", task_call)
    _create_session(db, "orphan", started=child_start)

    assert resolve_parent(db, "orphan") is None


def test_resolve_parent_only_matches_same_worktree(db) -> None:
    coordinator_start = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
    _create_session(db, "coordinator", started=coordinator_start, worktree="/proj-a")
    _record_task_call(db, "coordinator", coordinator_start + timedelta(seconds=10))
    _create_session(
        db,
        "child",
        started=coordinator_start + timedelta(seconds=15),
        worktree="/proj-b",
    )
    assert resolve_parent(db, "child") is None


def test_resolve_parent_idempotent_when_already_set(db) -> None:
    coordinator_start = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
    _create_session(db, "P", started=coordinator_start)
    _create_session(db, "C", started=coordinator_start, parent="P")
    # Already has a parent; resolve_parent returns it without re-resolving.
    assert resolve_parent(db, "C") == "P"


def test_resolve_parent_picks_most_recent_task_call(db) -> None:
    """Two coordinators dispatched Tasks; child matches the more recent one."""
    base = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
    _create_session(db, "C_first", started=base)
    _record_task_call(db, "C_first", base + timedelta(seconds=5), tool_use_id="t_first")

    _create_session(db, "C_second", started=base + timedelta(seconds=10))
    _record_task_call(db, "C_second", base + timedelta(seconds=20), tool_use_id="t_second")

    _create_session(db, "child", started=base + timedelta(seconds=25))
    assert resolve_parent(db, "child") == "C_second"


def test_build_project_tree_one_coordinator_three_children(db) -> None:
    """Spec acceptance: 1-coordinator + 3-implementor + 1-verifier yields right tree."""
    base = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
    _create_session(db, "coord", started=base)
    _create_session(db, "impl1", started=base + timedelta(seconds=10), parent="coord")
    _create_session(db, "impl2", started=base + timedelta(seconds=15), parent="coord")
    _create_session(db, "impl3", started=base + timedelta(seconds=20), parent="coord")
    _create_session(db, "verifier", started=base + timedelta(seconds=60), parent="coord")

    roots = build_project_tree(db, WORKTREE)
    assert len(roots) == 1
    assert roots[0].session_id == "coord"
    assert [c.session_id for c in roots[0].children] == [
        "impl1",
        "impl2",
        "impl3",
        "verifier",
    ]


def test_build_project_tree_orphan_at_root(db) -> None:
    """A session with no parent appears as its own root."""
    base = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
    _create_session(db, "root_a", started=base)
    _create_session(db, "orphan", started=base + timedelta(seconds=5))

    roots = build_project_tree(db, WORKTREE)
    sids = {r.session_id for r in roots}
    assert sids == {"root_a", "orphan"}


def test_build_project_tree_empty_for_unknown_worktree(db) -> None:
    assert build_project_tree(db, "/no/such/worktree") == []
