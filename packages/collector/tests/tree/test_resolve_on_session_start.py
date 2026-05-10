"""Cross-module test: SessionStart hook → resolve_parent fires automatically."""

from __future__ import annotations

from pathlib import Path

import pytest

from csm.db import connect
from csm.hooks.state_machine import apply_event


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


def test_session_start_auto_resolves_parent(db) -> None:
    """A child SessionStart within 30s of a parent's Task PreToolUse
    should automatically populate parent_session_id."""
    base_payload = {
        "cwd": "/tmp/proj",
        "transcript_path": "/tmp/p/x.jsonl",
    }
    apply_event(db, "SessionStart", {**base_payload, "session_id": "parent-1"})
    apply_event(
        db,
        "PreToolUse",
        {
            **base_payload,
            "session_id": "parent-1",
            "tool_name": "Task",
            "tool_use_id": "tu_dispatch_1",
        },
    )
    apply_event(db, "SessionStart", {**base_payload, "session_id": "child-1"})

    persisted = db.execute(
        "SELECT parent_session_id FROM sessions WHERE session_id='child-1'"
    ).fetchone()[0]
    assert persisted == "parent-1"


def test_session_start_without_recent_task_remains_orphan(db) -> None:
    """No Task call → child has no parent."""
    base_payload = {
        "cwd": "/tmp/proj",
        "transcript_path": "/tmp/p/x.jsonl",
    }
    apply_event(db, "SessionStart", {**base_payload, "session_id": "lonely"})
    persisted = db.execute(
        "SELECT parent_session_id FROM sessions WHERE session_id='lonely'"
    ).fetchone()[0]
    assert persisted is None
