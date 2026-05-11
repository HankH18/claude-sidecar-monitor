"""Tests for csm.permissions (V2.D)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from csm.db import connect
from csm.permissions import (
    ApprovalConfig,
    cleanup_stale_pending,
    is_tool_approval_required,
    load_approval_config,
    record_decision,
    request_decision,
)


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    # Insert a session so FK constraints pass.
    conn.execute(
        """
        INSERT INTO sessions (session_id, worktree_root, cwd, last_event_at, started_at)
        VALUES ('s1', '/tmp', '/tmp', '2026-05-10T00:00:00Z', '2026-05-10T00:00:00Z')
        """
    )
    yield conn
    conn.close()


def _enable_approval(db, tools: str = "Bash,Edit", timeout_ms: int = 1000) -> None:
    db.execute("UPDATE settings SET value='1' WHERE key='approval_enabled'")
    db.execute("UPDATE settings SET value=? WHERE key='approval_tools'", (tools,))
    db.execute(
        "UPDATE settings SET value=? WHERE key='approval_timeout_ms'",
        (str(timeout_ms),),
    )


# ────────── config ──────────


def test_load_approval_config_defaults(db) -> None:
    cfg = load_approval_config(db)
    assert cfg.enabled is False
    assert cfg.tools == frozenset()
    assert cfg.timeout_ms == 60000


def test_load_approval_config_with_tools(db) -> None:
    _enable_approval(db, tools="Bash, Edit ,  Write")
    cfg = load_approval_config(db)
    assert cfg.enabled is True
    assert cfg.tools == {"Bash", "Edit", "Write"}


def test_is_tool_approval_required_disabled(db) -> None:
    assert is_tool_approval_required(db, "Bash") is None


def test_is_tool_approval_required_enabled_match(db) -> None:
    _enable_approval(db, tools="Bash")
    cfg = is_tool_approval_required(db, "Bash")
    assert cfg is not None
    assert isinstance(cfg, ApprovalConfig)


def test_is_tool_approval_required_unconfigured_tool(db) -> None:
    _enable_approval(db, tools="Bash")
    assert is_tool_approval_required(db, "Read") is None


def test_is_tool_approval_required_no_tool(db) -> None:
    _enable_approval(db, tools="Bash")
    assert is_tool_approval_required(db, None) is None


# ────────── request_decision ──────────


@pytest.mark.asyncio
async def test_request_decision_returns_allow_when_decided(db) -> None:
    """Happy path: request, decide-mid-wait, receiver gets the decision."""

    async def decider() -> None:
        await asyncio.sleep(0.05)
        # Find the pending row's id, decide allow.
        row = db.execute(
            "SELECT id FROM permission_requests WHERE status='pending'"
        ).fetchone()
        assert row is not None
        await record_decision(db, request_id=row[0], decision="allow", reason="ok")

    decide_task = asyncio.create_task(decider())
    result = await request_decision(
        db,
        session_id="s1",
        tool_use_id="t1",
        tool_name="Bash",
        tool_input={"command": "ls"},
        timeout_ms=2000,
    )
    await decide_task
    assert result.decision == "allow"
    assert result.reason == "ok"

    row = db.execute(
        "SELECT status, decision_reason FROM permission_requests"
    ).fetchone()
    assert row[0] == "allow"
    assert row[1] == "ok"


@pytest.mark.asyncio
async def test_request_decision_returns_empty_on_timeout(db) -> None:
    """Timeout path: no decision, row marked timed_out, fail-open empty."""
    result = await request_decision(
        db,
        session_id="s1",
        tool_use_id="t2",
        tool_name="Bash",
        tool_input={"command": "x"},
        timeout_ms=100,  # short
    )
    assert result.decision is None
    assert result.to_hook_response() == {}

    status = db.execute("SELECT status FROM permission_requests").fetchone()[0]
    assert status == "timed_out"


@pytest.mark.asyncio
async def test_request_decision_returns_deny_when_decided(db) -> None:
    async def decider() -> None:
        await asyncio.sleep(0.05)
        row = db.execute(
            "SELECT id FROM permission_requests WHERE status='pending'"
        ).fetchone()
        await record_decision(
            db,
            request_id=row[0],
            decision="deny",
            reason="too dangerous",
        )

    decide_task = asyncio.create_task(decider())
    result = await request_decision(
        db,
        session_id="s1",
        tool_use_id="t3",
        tool_name="Bash",
        tool_input={},
        timeout_ms=2000,
    )
    await decide_task
    assert result.decision == "deny"
    assert result.to_hook_response() == {
        "permissionDecision": "deny",
        "permissionDecisionReason": "too dangerous",
    }


# ────────── record_decision ──────────


@pytest.mark.asyncio
async def test_record_decision_rejects_unknown_decision(db) -> None:
    with pytest.raises(ValueError, match="unknown decision"):
        await record_decision(db, request_id=1, decision="approve", reason=None)


@pytest.mark.asyncio
async def test_record_decision_returns_false_for_missing_row(db) -> None:
    accepted = await record_decision(
        db, request_id=999, decision="allow", reason=None
    )
    assert accepted is False


@pytest.mark.asyncio
async def test_record_decision_returns_false_for_already_decided(db) -> None:
    """Re-deciding a non-pending row returns False (idempotent at the DB
    level — caller surfaces 409)."""
    db.execute(
        """
        INSERT INTO permission_requests
            (session_id, tool_name, tool_input_json, status, requested_at, decided_at)
        VALUES ('s1', 'Bash', '{}', 'allow', '2026-05-10T00:00:00Z', '2026-05-10T00:00:01Z')
        """
    )
    rid = db.execute(
        "SELECT id FROM permission_requests ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    accepted = await record_decision(db, request_id=rid, decision="deny", reason=None)
    assert accepted is False
    # Row still shows the original decision (no clobber).
    status = db.execute(
        "SELECT status FROM permission_requests WHERE id = ?", (rid,)
    ).fetchone()[0]
    assert status == "allow"


# ────────── cleanup_stale_pending ──────────


def test_cleanup_stale_pending_marks_old_rows(db) -> None:
    # Old row that should be cleaned up.
    db.execute(
        """
        INSERT INTO permission_requests
            (session_id, tool_name, tool_input_json, status, requested_at)
        VALUES ('s1', 'Bash', '{}', 'pending', '2020-01-01T00:00:00Z')
        """
    )
    # Recent row — must NOT be touched.
    from datetime import UTC, datetime

    recent = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        """
        INSERT INTO permission_requests
            (session_id, tool_name, tool_input_json, status, requested_at)
        VALUES ('s1', 'Bash', '{}', 'pending', ?)
        """,
        (recent,),
    )

    touched = cleanup_stale_pending(db, max_age_seconds=3600)
    assert touched == 1

    statuses = [row[0] for row in db.execute(
        "SELECT status FROM permission_requests ORDER BY requested_at"
    ).fetchall()]
    assert statuses == ["timed_out", "pending"]
