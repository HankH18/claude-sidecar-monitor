"""Tests for the hang scanner (T8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from csm.db import connect
from csm.scanner import (
    PRECOMPACT_EXTENSION_MS,
    HangThresholds,
    load_thresholds,
    scan_once,
)


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


SID = "scanner-test-session"


def _create_session(
    conn,
    *,
    state: str = "running",
    last_event_age_s: int = 0,
    last_event_name: str | None = None,
    sid: str = SID,
    now: datetime | None = None,
) -> datetime:
    """Create a session whose ``last_event_at`` is ``last_event_age_s`` ago."""
    now = now or datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    last = now - timedelta(seconds=last_event_age_s)
    conn.execute(
        """
        INSERT INTO sessions (
            session_id, worktree_root, cwd, state, last_event_at,
            last_event_name, started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sid,
            "/tmp/proj",
            "/tmp/proj",
            state,
            last.strftime("%Y-%m-%dT%H:%M:%SZ"),
            last_event_name,
            now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )
    return now


def _state(conn, sid: str = SID) -> str:
    return conn.execute("SELECT state FROM sessions WHERE session_id = ?", (sid,)).fetchone()[0]


# ────────── thresholds ──────────


def test_default_thresholds(db) -> None:
    thr = load_thresholds(db)
    assert thr == HangThresholds(yellow_ms=60_000, red_ms=180_000)


def test_thresholds_respect_settings(db) -> None:
    db.execute("UPDATE settings SET value=? WHERE key=?", ("90000", "hang_yellow_ms"))
    db.execute("UPDATE settings SET value=? WHERE key=?", ("300000", "hang_red_ms"))
    thr = load_thresholds(db)
    assert thr.yellow_ms == 90_000
    assert thr.red_ms == 300_000


# ────────── transitions ──────────


def test_running_session_past_red_becomes_hung(db) -> None:
    now = _create_session(db, state="running", last_event_age_s=200)  # > 180s default
    transitioned = scan_once(db, now=now)
    assert SID in transitioned
    assert _state(db) == "hung"


def test_tool_session_past_red_becomes_hung(db) -> None:
    now = _create_session(db, state="tool", last_event_age_s=200)
    transitioned = scan_once(db, now=now)
    assert SID in transitioned
    assert _state(db) == "hung"


def test_session_below_red_threshold_unchanged(db) -> None:
    now = _create_session(db, state="running", last_event_age_s=120)  # < 180s
    transitioned = scan_once(db, now=now)
    assert transitioned == []
    assert _state(db) == "running"


def test_done_session_unchanged(db) -> None:
    """Scanner only touches running/tool, never done/hung/waiting_user."""
    now = _create_session(db, state="done", last_event_age_s=99999)
    transitioned = scan_once(db, now=now)
    assert transitioned == []
    assert _state(db) == "done"


def test_already_hung_session_not_re_emitted(db) -> None:
    now = _create_session(db, state="hung", last_event_age_s=200)
    transitioned = scan_once(db, now=now)
    assert transitioned == []
    assert _state(db) == "hung"


def test_waiting_user_session_not_treated_as_hung(db) -> None:
    """waiting_user is intentional; not a hang."""
    now = _create_session(db, state="waiting_user", last_event_age_s=99999)
    transitioned = scan_once(db, now=now)
    assert transitioned == []
    assert _state(db) == "waiting_user"


# ────────── PreCompact extension ──────────


def test_precompact_extends_red_threshold(db) -> None:
    """A session in PreCompact gets +60s on the red threshold."""
    # Default red is 180s. With PreCompact extension, threshold becomes 240s.
    # Set elapsed = 220s — should NOT trigger.
    now = _create_session(db, state="running", last_event_age_s=220, last_event_name="PreCompact")
    transitioned = scan_once(db, now=now)
    assert transitioned == []
    assert _state(db) == "running"

    # PRECOMPACT_EXTENSION_MS sanity
    assert PRECOMPACT_EXTENSION_MS == 60_000


def test_precompact_still_hangs_past_extended_threshold(db) -> None:
    """At 250s elapsed (> 240s extended), even PreCompact transitions."""
    now = _create_session(db, state="running", last_event_age_s=250, last_event_name="PreCompact")
    transitioned = scan_once(db, now=now)
    assert SID in transitioned
    assert _state(db) == "hung"


# ────────── Multi-session scan ──────────


def test_scan_handles_multiple_sessions(db) -> None:
    base = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    _create_session(db, sid="ok", state="running", last_event_age_s=10, now=base)
    _create_session(db, sid="hung1", state="running", last_event_age_s=200, now=base)
    _create_session(db, sid="hung2", state="tool", last_event_age_s=300, now=base)
    _create_session(db, sid="done_old", state="done", last_event_age_s=999, now=base)

    transitioned = scan_once(db, now=base)
    assert set(transitioned) == {"hung1", "hung2"}

    states = dict(db.execute("SELECT session_id, state FROM sessions").fetchall())
    assert states["ok"] == "running"
    assert states["hung1"] == "hung"
    assert states["hung2"] == "hung"
    assert states["done_old"] == "done"
