"""Tests for csm.digest (V2.B activity digest)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from csm.db import connect
from csm.digest import (
    SUMMARY_MAX_LEN,
    apply_digest_update,
    derive_session_digest,
)

# Anchor "now" so the windows are deterministic across runs.
NOW = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path: Path) -> Any:
    conn = connect(db_path=tmp_path / "store.db")
    conn.execute(
        """
        INSERT INTO sessions (session_id, worktree_root, cwd, last_event_at, started_at)
        VALUES ('s1', '/tmp', '/tmp', ?, ?)
        """,
        (_iso(NOW), _iso(NOW)),
    )
    yield conn
    conn.close()


def _insert_event(
    conn: Any,
    *,
    session_id: str = "s1",
    event_name: str,
    tool_name: str | None = None,
    tool_use_id: str | None = None,
    payload: dict[str, Any] | None = None,
    received_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO events (
            session_id, event_name, received_at, tool_name, tool_use_id,
            duration_ms, payload_json
        ) VALUES (?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            session_id,
            event_name,
            _iso(received_at),
            tool_name,
            tool_use_id,
            json.dumps(payload or {}),
        ),
    )


def _insert_message(
    conn: Any,
    *,
    session_id: str = "s1",
    role: str,
    content: Any,
    timestamp: datetime,
    model: str | None = None,
) -> None:
    if role == "user":
        raw = {"type": "user", "message": {"role": "user", "content": content}}
    elif role == "assistant":
        raw = {
            "type": "assistant",
            "message": {"role": "assistant", "model": model, "content": content},
        }
    else:
        raw = {"type": role, "message": {"role": role, "content": content}}
    conn.execute(
        """
        INSERT INTO transcript_messages (
            session_id, role, timestamp, content_json, model
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, role, _iso(timestamp), json.dumps(raw), model),
    )


def _insert_pending_approval(
    conn: Any,
    *,
    session_id: str = "s1",
    tool_name: str = "Bash",
    requested_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO permission_requests (
            session_id, tool_use_id, tool_name, tool_input_json,
            status, requested_at
        ) VALUES (?, NULL, ?, '{}', 'pending', ?)
        """,
        (session_id, tool_name, _iso(requested_at)),
    )


# ────────── empty / no-signal ──────────


def test_empty_session_returns_none(db: Any) -> None:
    summary, ts = derive_session_digest(db, "s1", now=NOW)
    assert summary is None
    assert ts is None


def test_stale_signals_return_none(db: Any) -> None:
    """A user prompt older than the recent-text window doesn't count."""
    _insert_message(
        db,
        role="user",
        content="please do the thing",
        timestamp=NOW - timedelta(minutes=30),
    )
    summary, ts = derive_session_digest(db, "s1", now=NOW)
    assert summary is None
    assert ts is None


# ────────── heuristic 1: pending approval ──────────


def test_pending_approval_dominates(db: Any) -> None:
    _insert_pending_approval(db, tool_name="Bash", requested_at=NOW - timedelta(seconds=5))
    summary, ts = derive_session_digest(db, "s1", now=NOW)
    assert summary == "Awaiting approval for Bash"
    assert ts == _iso(NOW)


def test_approval_beats_active_tool(db: Any) -> None:
    """Approval is priority 1, active tool is priority 2."""
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Read",
        tool_use_id="t1",
        payload={"tool_input": {"file_path": "/foo/bar.py"}},
        received_at=NOW - timedelta(seconds=2),
    )
    _insert_pending_approval(db, tool_name="Edit", requested_at=NOW - timedelta(seconds=1))
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary == "Awaiting approval for Edit"


# ────────── heuristic 2: active tool ──────────


def test_active_bash_tool_includes_command(db: Any) -> None:
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Bash",
        tool_use_id="t1",
        payload={"tool_input": {"command": "pytest -x tests/digest"}},
        received_at=NOW - timedelta(seconds=3),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary is not None
    assert summary.startswith("Running Bash: pytest -x")


def test_active_read_uses_basename(db: Any) -> None:
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Read",
        tool_use_id="t2",
        payload={"tool_input": {"file_path": "/Users/me/proj/setup.py"}},
        received_at=NOW - timedelta(seconds=2),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary == "Reading setup.py"


def test_active_edit_uses_basename(db: Any) -> None:
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Edit",
        tool_use_id="t3",
        payload={"tool_input": {"file_path": "/x/y/queries.py"}},
        received_at=NOW - timedelta(seconds=1),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary == "Editing queries.py"


def test_active_agent_is_delegating(db: Any) -> None:
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Agent",
        tool_use_id="t4",
        payload={"tool_input": {"description": "audit the diff"}},
        received_at=NOW - timedelta(seconds=4),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary == "Delegating to subagent"


def test_completed_tool_is_not_active(db: Any) -> None:
    """PostToolUse matching the Pre's tool_use_id closes it out."""
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Read",
        tool_use_id="t5",
        payload={"tool_input": {"file_path": "/a/b.py"}},
        received_at=NOW - timedelta(seconds=10),
    )
    _insert_event(
        db,
        event_name="PostToolUse",
        tool_name="Read",
        tool_use_id="t5",
        payload={},
        received_at=NOW - timedelta(seconds=9),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary is None


def test_old_active_tool_outside_window_ignored(db: Any) -> None:
    """Pre 10 minutes ago without Post — past the 5min window, don't
    surface. The hang scanner will have flipped state='hung' by then."""
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Bash",
        tool_use_id="t6",
        payload={"tool_input": {"command": "ls"}},
        received_at=NOW - timedelta(minutes=10),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary is None


def test_long_running_tool_inside_window_still_active(db: Any) -> None:
    """A tool that started 90s ago and hasn't returned should still
    surface as 'Running X' — the dashboard's #1 question is 'is
    anything hung', so 60-300s stalls are exactly what we want visible."""
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Bash",
        tool_use_id="t_long",
        payload={"tool_input": {"command": "pytest -x"}},
        received_at=NOW - timedelta(seconds=90),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary is not None
    assert summary.startswith("Running Bash")


# ────────── heuristic 3: recent assistant text ──────────


def test_recent_assistant_text_uses_first_sentence(db: Any) -> None:
    _insert_message(
        db,
        role="assistant",
        content=[
            {"type": "text", "text": "Implemented the digest module. Tests next."}
        ],
        timestamp=NOW - timedelta(seconds=30),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary == "Implemented the digest module."


def test_active_tool_beats_assistant_text(db: Any) -> None:
    _insert_message(
        db,
        role="assistant",
        content=[{"type": "text", "text": "Working on it."}],
        timestamp=NOW - timedelta(seconds=120),
    )
    _insert_event(
        db,
        event_name="PreToolUse",
        tool_name="Bash",
        tool_use_id="tA",
        payload={"tool_input": {"command": "make test"}},
        received_at=NOW - timedelta(seconds=5),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary is not None
    assert summary.startswith("Running Bash")


# ────────── heuristic 4: recent user prompt ──────────


def test_recent_user_prompt_with_no_assistant_reply(db: Any) -> None:
    _insert_message(
        db,
        role="user",
        content="refactor the digest dispatch loop please",
        timestamp=NOW - timedelta(seconds=20),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary is not None
    assert summary.startswith("Working on:")
    assert "refactor the digest dispatch loop" in summary


def test_user_prompt_skipped_when_assistant_replied_since(db: Any) -> None:
    """User asks → assistant replies. Heuristic 3 wins."""
    _insert_message(
        db,
        role="user",
        content="do the thing",
        timestamp=NOW - timedelta(seconds=60),
    )
    _insert_message(
        db,
        role="assistant",
        content=[{"type": "text", "text": "Done — see PR."}],
        timestamp=NOW - timedelta(seconds=30),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary == "Done — see PR."


# ────────── truncation ──────────


def test_long_assistant_text_truncated(db: Any) -> None:
    long_text = "Refactoring " + ("the dispatch loop " * 30)
    _insert_message(
        db,
        role="assistant",
        content=[{"type": "text", "text": long_text}],
        timestamp=NOW - timedelta(seconds=5),
    )
    summary, _ = derive_session_digest(db, "s1", now=NOW)
    assert summary is not None
    assert len(summary) <= SUMMARY_MAX_LEN
    assert summary.endswith("…")


# ────────── idempotency / apply_digest_update ──────────


def test_idempotent_same_inputs_same_output(db: Any) -> None:
    _insert_pending_approval(db, tool_name="Bash", requested_at=NOW - timedelta(seconds=5))
    a, _ = derive_session_digest(db, "s1", now=NOW)
    b, _ = derive_session_digest(db, "s1", now=NOW)
    assert a == b == "Awaiting approval for Bash"


def test_apply_digest_update_writes_changed(db: Any) -> None:
    _insert_pending_approval(db, tool_name="Bash", requested_at=NOW - timedelta(seconds=2))
    summary, generated_at, changed = apply_digest_update(db, "s1", now=NOW)
    assert changed is True
    assert summary == "Awaiting approval for Bash"
    row = db.execute(
        "SELECT activity_summary, activity_updated_at FROM sessions WHERE session_id='s1'"
    ).fetchone()
    assert row[0] == summary
    assert row[1] == generated_at


def test_list_sessions_does_not_write_back_digest(db: Any) -> None:
    """Regression: the API read path used to call ``apply_digest_update``
    which UPDATEs sessions.activity_summary on every GET. Two concurrent
    GETs could race the receiver's BEGIN IMMEDIATE write lock and hit
    SQLITE_BUSY; also N+1 churn on a hot endpoint. The fix: read path
    overlays the computed digest on the response WITHOUT writing back.

    This test asserts ``list_sessions`` never bumps ``activity_updated_at``
    on its own — only state-machine emits do.
    """
    from csm.api.queries import list_sessions

    _insert_pending_approval(db, tool_name="Bash", requested_at=NOW - timedelta(seconds=2))

    # Persisted column is empty initially.
    pre = db.execute(
        "SELECT activity_summary, activity_updated_at FROM sessions WHERE session_id='s1'"
    ).fetchone()
    assert pre == (None, None)

    sessions = list_sessions(db, limit=10)
    assert len(sessions) == 1
    # The returned object should have the freshly-computed digest
    # overlaid, but the DB row must NOT have been written.
    assert sessions[0].activity_summary == "Awaiting approval for Bash"

    post = db.execute(
        "SELECT activity_summary, activity_updated_at FROM sessions WHERE session_id='s1'"
    ).fetchone()
    assert post == (None, None), "read path must not write back to sessions"


def test_apply_digest_update_noop_when_unchanged(db: Any) -> None:
    _insert_pending_approval(db, tool_name="Bash", requested_at=NOW - timedelta(seconds=2))
    # First write — sets the row.
    _, first_ts, changed1 = apply_digest_update(db, "s1", now=NOW)
    assert changed1 is True
    # Second call at a LATER time but with the same computed summary —
    # must not bump activity_updated_at (avoid SSE storms).
    later = NOW + timedelta(seconds=5)
    summary, _, changed2 = apply_digest_update(db, "s1", now=later)
    assert changed2 is False
    row = db.execute(
        "SELECT activity_summary, activity_updated_at FROM sessions WHERE session_id='s1'"
    ).fetchone()
    assert row[0] == summary
    assert row[1] == first_ts  # unchanged
