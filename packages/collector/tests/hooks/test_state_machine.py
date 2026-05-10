"""Tests for hooks.state_machine — every event in the §4.1 mapping table."""

from __future__ import annotations

from pathlib import Path

import pytest

from csm.db import connect
from csm.hooks.state_machine import (
    KNOWN_EVENTS,
    UnknownEventError,
    apply_event,
)


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


SID = "session-test-001"


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "session_id": SID,
        "cwd": "/tmp/proj",
        "transcript_path": "/tmp/.claude/projects/proj/session-test-001.jsonl",
    }
    base.update(overrides)
    return base


def _state(db: object, sid: str = SID) -> tuple[str, str | None, str | None]:
    row = db.execute(  # type: ignore[attr-defined]
        "SELECT state, last_event_name, last_tool_name FROM sessions WHERE session_id=?",
        (sid,),
    ).fetchone()
    return row


# ────────── Happy-path lifecycle ──────────


def test_session_start_creates_running_session(db: object) -> None:
    apply_event(db, "SessionStart", _payload(source="startup"))
    state, last_event, _ = _state(db)
    assert state == "running"
    assert last_event == "SessionStart"


def test_pretooluse_transitions_to_tool(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "PreToolUse", _payload(tool_name="Bash", tool_use_id="tu_1"))
    state, last_event, last_tool = _state(db)
    assert state == "tool"
    assert last_event == "PreToolUse"
    assert last_tool == "Bash"


def test_posttooluse_transitions_back_to_running(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "PreToolUse", _payload(tool_name="Bash", tool_use_id="tu_1"))
    apply_event(db, "PostToolUse", _payload(tool_name="Bash", tool_use_id="tu_1"))
    state, last_event, last_tool = _state(db)
    assert state == "running"
    assert last_event == "PostToolUse"
    assert last_tool is None


def test_user_prompt_submit_keeps_running(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "UserPromptSubmit", _payload())
    state, last_event, _ = _state(db)
    assert state == "running"
    assert last_event == "UserPromptSubmit"


def test_stop_transitions_to_done(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "Stop", _payload(last_assistant_message="goodbye"))
    state, last_event, _ = _state(db)
    assert state == "done"
    assert last_event == "Stop"
    completed = db.execute(  # type: ignore[attr-defined]
        "SELECT completed_at FROM sessions WHERE session_id=?", (SID,)
    ).fetchone()[0]
    assert completed is not None


def test_subagent_stop_marks_done(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "SubagentStop", _payload())
    state, last_event, _ = _state(db)
    assert state == "done"
    assert last_event == "SubagentStop"


def test_session_end_marks_done(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "SessionEnd", _payload())
    state, _, _ = _state(db)
    assert state == "done"


# ────────── Notification: conditional transition ──────────


def test_notification_permission_request_waits_for_user(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "Notification", _payload(notification_type="permission_request"))
    state, last_event, _ = _state(db)
    assert state == "waiting_user"
    assert last_event == "Notification"


def test_notification_other_does_not_change_state(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "Notification", _payload(notification_type="other_kind"))
    state, _, _ = _state(db)
    assert state == "running"


# ────────── Pre-compact extension is informational ──────────


def test_precompact_records_but_no_state_change(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "PreCompact", _payload())
    state, last_event, _ = _state(db)
    assert state == "running"
    assert last_event == "PreCompact"


def test_setup_does_not_change_state(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "Setup", _payload())
    state, last_event, _ = _state(db)
    assert state == "running"
    assert last_event == "Setup"


# ────────── PermissionRequest (v2-ready) ──────────


def test_permission_request_event_routes_to_waiting_user(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "PermissionRequest", _payload())
    state, _, _ = _state(db)
    assert state == "waiting_user"


# ────────── Validation ──────────


def test_unknown_event_raises(db: object) -> None:
    with pytest.raises(UnknownEventError):
        apply_event(db, "DefinitelyNotAClaudeHook", _payload())


def test_missing_session_id_raises(db: object) -> None:
    with pytest.raises(ValueError, match="session_id"):
        apply_event(db, "SessionStart", {"cwd": "/tmp"})


# ────────── Worktree resolution ──────────


def test_worktree_root_resolved_for_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "myrepo"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "src" / "deep"
    sub.mkdir(parents=True)
    db_path = tmp_path / "store.db"
    db = connect(db_path=db_path)
    try:
        apply_event(
            db,
            "SessionStart",
            {"session_id": SID, "cwd": str(sub), "transcript_path": "/tmp/x.jsonl"},
        )
        worktree, project = db.execute(
            "SELECT worktree_root, project_label FROM sessions WHERE session_id=?",
            (SID,),
        ).fetchone()
    finally:
        db.close()
    assert worktree == str(repo)
    assert project == "myrepo"


# ────────── Replay-style: synthetic full session ──────────


def test_replay_full_session(db: object) -> None:
    """SessionStart → 3 tool uses → Stop. Final state = done, 7 events recorded."""
    apply_event(db, "SessionStart", _payload(source="startup"))
    for i in range(3):
        apply_event(db, "PreToolUse", _payload(tool_name="Bash", tool_use_id=f"tu_{i}"))
        apply_event(db, "PostToolUse", _payload(tool_name="Bash", tool_use_id=f"tu_{i}"))
    apply_event(db, "Stop", _payload())

    state, last_event, _ = _state(db)
    assert state == "done"
    assert last_event == "Stop"

    events = db.execute(  # type: ignore[attr-defined]
        "SELECT count(*) FROM events WHERE session_id=?", (SID,)
    ).fetchone()[0]
    assert events == 8  # SessionStart + 3*(Pre + Post) + Stop


def test_known_events_set_matches_spec() -> None:
    """Sanity: spec.md §5 known events are in the validator set."""
    assert {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "Notification",
        "Stop",
        "SubagentStop",
        "SessionEnd",
        "PreCompact",
        "Setup",
        "PermissionRequest",
    } == KNOWN_EVENTS
