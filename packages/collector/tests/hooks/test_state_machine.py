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


def test_apply_event_rolls_back_on_exception(db: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """If anything inside apply_event raises after the BEGIN, the
    transaction must roll back so the session row isn't half-written."""
    # Establish a baseline session in a known state.
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "PreToolUse", _payload(tool_name="Bash", tool_use_id="t1"))
    baseline = _state(db)

    # Force `resolve_parent` (called for SessionStart) to raise mid-event.
    # SessionStart is the only event that calls resolve_parent, and it
    # happens AFTER the sessions UPDATE — perfect canary.

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated mid-event failure")

    monkeypatch.setattr("csm.tree.resolve_parent", boom)

    with pytest.raises(RuntimeError, match="simulated"):
        apply_event(db, "SessionStart", _payload(source="resume"))

    # Row state must be exactly what it was before the failed call —
    # NOT the partial half-written state where the UPDATE landed.
    after = _state(db)
    assert after == baseline


# ────────── V2.A2 nickname + title ──────────


def test_session_start_assigns_deterministic_nickname(db: object) -> None:
    """V2.A2: SessionStart writes a deterministic nickname to the row."""
    apply_event(db, "SessionStart", _payload())
    nick = db.execute(  # type: ignore[attr-defined]
        "SELECT nickname FROM sessions WHERE session_id=?", (SID,)
    ).fetchone()[0]
    assert nick is not None
    # Format: <adj>-<noun>-<NNNN>
    assert nick.count("-") == 2

    # Re-applying SessionStart (resume) must not change the nickname.
    apply_event(db, "SessionStart", _payload(source="resume"))
    nick2 = db.execute(  # type: ignore[attr-defined]
        "SELECT nickname FROM sessions WHERE session_id=?", (SID,)
    ).fetchone()[0]
    assert nick2 == nick


def test_user_prompt_submit_derives_title(db: object) -> None:
    """V2.A2: first UserPromptSubmit sets the session title."""
    apply_event(db, "SessionStart", _payload())
    apply_event(
        db,
        "UserPromptSubmit",
        _payload(prompt="debug the failing test in foo_test.py"),
    )
    title, source = db.execute(  # type: ignore[attr-defined]
        "SELECT title, title_source FROM sessions WHERE session_id=?", (SID,)
    ).fetchone()
    assert title == "debug the failing test in foo_test.py"
    assert source == "user_prompt"


def test_user_prompt_submit_doesnt_overwrite_existing_title(db: object) -> None:
    """V2.A2: a second UserPromptSubmit (mid-session continuation) must
    not clobber the original title."""
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "UserPromptSubmit", _payload(prompt="initial intent"))
    apply_event(db, "UserPromptSubmit", _payload(prompt="oh and also clean this up"))
    title = db.execute(  # type: ignore[attr-defined]
        "SELECT title FROM sessions WHERE session_id=?", (SID,)
    ).fetchone()[0]
    assert title == "initial intent"


def test_user_prompt_submit_skips_empty_prompts(db: object) -> None:
    apply_event(db, "SessionStart", _payload())
    apply_event(db, "UserPromptSubmit", _payload(prompt="   "))
    title = db.execute(  # type: ignore[attr-defined]
        "SELECT title FROM sessions WHERE session_id=?", (SID,)
    ).fetchone()[0]
    assert title is None


# ────────── V2.C2 virtual subagent rows ──────────


def test_agent_tool_pre_creates_virtual_subagent(db: object) -> None:
    """V2.C2: PreToolUse(Agent) inserts a subagent_sessions row with
    title from description, agent_kind from subagent_type."""
    apply_event(db, "SessionStart", _payload())
    apply_event(
        db,
        "PreToolUse",
        _payload(
            tool_name="Agent",
            tool_use_id="toolu_agent_1",
            tool_input={
                "description": "Review API safety",
                "prompt": "You're an auditor. Walk the diff…",
                "subagent_type": "code-reviewer",
            },
        ),
    )
    row = db.execute(  # type: ignore[attr-defined]
        "SELECT virtual_id, parent_session_id, tool_use_id, title, agent_kind, "
        "subagent_type, state FROM subagent_sessions"
    ).fetchone()
    assert row is not None
    virtual_id, parent_sid, tool_use_id, title, kind, subtype, state = row
    assert parent_sid == SID
    assert tool_use_id == "toolu_agent_1"
    assert virtual_id == f"{SID}:toolu_agent_1"
    assert title == "Review API safety"
    assert kind == "reviewer"
    assert subtype == "code-reviewer"
    assert state == "running"


def test_agent_tool_post_closes_virtual_subagent(db: object) -> None:
    """V2.C2: PostToolUse(Agent) marks the matching virtual as done."""
    apply_event(db, "SessionStart", _payload())
    apply_event(
        db,
        "PreToolUse",
        _payload(
            tool_name="Agent",
            tool_use_id="toolu_x",
            tool_input={"description": "task", "subagent_type": "Explore"},
        ),
    )
    apply_event(
        db,
        "PostToolUse",
        _payload(tool_name="Agent", tool_use_id="toolu_x"),
    )
    state, completed_at = db.execute(  # type: ignore[attr-defined]
        "SELECT state, completed_at FROM subagent_sessions WHERE virtual_id=?",
        (f"{SID}:toolu_x",),
    ).fetchone()
    assert state == "done"
    assert completed_at is not None


def test_agent_tool_pre_idempotent_on_duplicate(db: object) -> None:
    """Duplicate PreToolUse(Agent) must not create a second virtual row."""
    apply_event(db, "SessionStart", _payload())
    apply_event(
        db,
        "PreToolUse",
        _payload(
            tool_name="Agent",
            tool_use_id="toolu_dup",
            tool_input={"description": "first", "subagent_type": "general-purpose"},
        ),
    )
    apply_event(
        db,
        "PreToolUse",
        _payload(
            tool_name="Agent",
            tool_use_id="toolu_dup",
            tool_input={"description": "second"},
        ),
    )
    rows = db.execute(  # type: ignore[attr-defined]
        "SELECT title FROM subagent_sessions WHERE virtual_id=?",
        (f"{SID}:toolu_dup",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "first"


def test_agent_tool_with_no_tool_use_id_skips_virtual(db: object) -> None:
    """Without a tool_use_id we can't form a virtual_id; skip silently."""
    apply_event(db, "SessionStart", _payload())
    apply_event(
        db,
        "PreToolUse",
        _payload(tool_name="Agent", tool_input={"description": "orphan"}),
    )
    count = db.execute(  # type: ignore[attr-defined]
        "SELECT count(*) FROM subagent_sessions"
    ).fetchone()[0]
    assert count == 0


def test_non_agent_tool_doesnt_create_virtual(db: object) -> None:
    """PreToolUse for non-Agent tools must NOT create a subagent row."""
    apply_event(db, "SessionStart", _payload())
    apply_event(
        db,
        "PreToolUse",
        _payload(tool_name="Bash", tool_use_id="toolu_bash"),
    )
    count = db.execute(  # type: ignore[attr-defined]
        "SELECT count(*) FROM subagent_sessions"
    ).fetchone()[0]
    assert count == 0


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
