"""Tests for csm.permissions (V2.D)."""

from __future__ import annotations

import asyncio
import contextlib
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
        row = db.execute("SELECT id FROM permission_requests WHERE status='pending'").fetchone()
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

    row = db.execute("SELECT status, decision_reason FROM permission_requests").fetchone()
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
        row = db.execute("SELECT id FROM permission_requests WHERE status='pending'").fetchone()
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
    accepted = await record_decision(db, request_id=999, decision="allow", reason=None)
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
    rid = db.execute("SELECT id FROM permission_requests ORDER BY id DESC LIMIT 1").fetchone()[0]
    accepted = await record_decision(db, request_id=rid, decision="deny", reason=None)
    assert accepted is False
    # Row still shows the original decision (no clobber).
    status = db.execute("SELECT status FROM permission_requests WHERE id = ?", (rid,)).fetchone()[0]
    assert status == "allow"


# ────────── cleanup_stale_pending ──────────


@pytest.mark.asyncio
async def test_request_decision_honors_decision_during_register_race(db) -> None:
    """Regression: the dashboard decides between the INSERT commit and
    register() — record_decision must stash the result so register()
    picks it up. Previously the decision was dropped on the floor and
    the receiver returned {} despite a real user decision.

    We reproduce by inserting the row + calling record_decision BEFORE
    request_decision can register its waiter (simulating the worst-case
    race), then calling request_decision in a way that finds the row
    and registers.
    """
    # Insert the row manually (mimic the autocommit INSERT that
    # request_decision does internally).
    db.execute(
        """
        INSERT INTO permission_requests
            (session_id, tool_name, tool_input_json, status, requested_at)
        VALUES ('s1', 'Bash', '{}', 'pending', '2026-05-10T00:00:00Z')
        """
    )
    request_id = db.execute(
        "SELECT id FROM permission_requests ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]

    # Dashboard decides BEFORE any waiter has registered.
    accepted = await record_decision(
        db, request_id=request_id, decision="allow", reason="pre-registered"
    )
    assert accepted is True

    # Now a waiter registers. It must immediately see the deferred
    # decision and the event must already be set.
    from csm.permissions import decisions

    event = await decisions.register(request_id)
    assert event.is_set(), "deferred decision should pre-set the event"
    decision, reason = await decisions.collect(request_id)
    assert decision == "allow"
    assert reason == "pre-registered"


@pytest.mark.asyncio
async def test_request_decision_cleanup_on_cancellation(db) -> None:
    """Regression: a client disconnect (asyncio.CancelledError) used to
    skip the timeout cleanup path — the holder leaked and the row stayed
    'pending' forever (until the next startup's cleanup_stale_pending
    sweep). With the try/finally + spawn-cleanup-task fix, both the
    holder is dropped AND the row transitions to timed_out even if the
    parent task is cancelled while parked on event.wait().
    """
    from csm.permissions import decisions

    async def runner() -> None:
        await request_decision(
            db,
            session_id="s1",
            tool_use_id="cancel_me",
            tool_name="Bash",
            tool_input={"command": "true"},
            timeout_ms=60_000,  # long — we'll cancel before it fires
        )

    task = asyncio.create_task(runner())
    # Wait for the runner to reach the event.wait() — at which point the
    # holder is registered AND the DB row is inserted. We detect this by
    # polling the holder map (the "after register()" gate). Cancelling
    # before this point would test a less-interesting scenario (the
    # bug-fix surface is "in flight when client disconnects").
    request_id: int | None = None
    for _ in range(200):
        await asyncio.sleep(0.001)
        if decisions._holders:
            request_id = next(iter(decisions._holders))
            break
    assert request_id is not None, "runner never registered a holder"

    pre_tasks = set(asyncio.all_tasks())

    # Cancel the task — simulates a FastAPI client disconnect.
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The finally block spawned a cleanup task on the loop. In
    # production the loop keeps running forever so the task gets cycles;
    # in tests the loop runs only as long as the test body, so we have
    # to await it explicitly.
    post_tasks = set(asyncio.all_tasks()) - pre_tasks - {asyncio.current_task()}
    for t in post_tasks:
        with contextlib.suppress(BaseException):
            await t

    assert request_id not in decisions._holders, "holder leaked on cancel"
    status = db.execute(
        "SELECT status FROM permission_requests WHERE id = ?",
        (request_id,),
    ).fetchone()[0]
    assert status == "timed_out", f"row stuck in {status!r} after cancel"


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

    statuses = [
        row[0]
        for row in db.execute(
            "SELECT status FROM permission_requests ORDER BY requested_at"
        ).fetchall()
    ]
    assert statuses == ["timed_out", "pending"]
