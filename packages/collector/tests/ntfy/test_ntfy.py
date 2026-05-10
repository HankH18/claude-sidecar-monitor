"""Tests for the ntfy.sh dispatcher (T12)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from csm import ntfy
from csm.bus import BusEvent
from csm.db import connect
from csm.ntfy import NtfyDispatcher, _build_payload, send_test_notification


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


def _set_topic(conn, topic: str) -> None:
    conn.execute("UPDATE settings SET value=? WHERE key='ntfy_topic'", (topic,))


# ────────── payload shapes ──────────


def test_hang_event_builds_priority_5_payload() -> None:
    event = BusEvent(
        kind="hang",
        session_id="abc",
        data={
            "elapsed_ms": 200_000,
            "last_tool_name": "Bash",
            "worktree_root": "/tmp/proj",
            "is_top_level": True,
            "parent_session_id": None,
        },
    )
    payload = _build_payload(event, project="proj", topic="csm-test")
    assert payload is not None
    assert payload["url"].endswith("/csm-test")
    assert payload["headers"]["Priority"] == "5"
    assert "[proj] hung" in payload["headers"]["Title"]
    assert "Bash" in payload["content"]


def test_top_level_done_builds_priority_3_payload() -> None:
    event = BusEvent(
        kind="session_update",
        session_id="abc",
        data={
            "state": "done",
            "parent_session_id": None,
            "worktree_root": "/tmp/proj",
        },
    )
    payload = _build_payload(event, project="proj", topic="csm-test")
    assert payload is not None
    assert payload["headers"]["Priority"] == "3"
    assert "complete" in payload["headers"]["Title"]


def test_subagent_done_does_not_push() -> None:
    event = BusEvent(
        kind="session_update",
        session_id="child",
        data={
            "state": "done",
            "parent_session_id": "parent",
            "worktree_root": "/tmp/proj",
        },
    )
    assert _build_payload(event, project="proj", topic="t") is None


def test_running_state_update_does_not_push() -> None:
    event = BusEvent(
        kind="session_update",
        session_id="abc",
        data={"state": "running", "parent_session_id": None},
    )
    assert _build_payload(event, project="proj", topic="t") is None


def test_unrelated_kinds_skip() -> None:
    event = BusEvent(kind="transcript_message", session_id="abc", data={})
    assert _build_payload(event, project="proj", topic="t") is None


# ────────── dispatcher integration ──────────


@pytest.mark.asyncio
async def test_dispatcher_skips_when_topic_empty(db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty topic = no HTTP call regardless of event."""
    sent: list[dict] = []

    async def fake_post(self, url, content=None, headers=None, timeout=None):
        sent.append({"url": url, "content": content, "headers": headers})

        class R:
            def raise_for_status(self_inner):
                return None

        return R()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    dispatcher = NtfyDispatcher(db)
    await dispatcher._dispatch(
        BusEvent(
            kind="hang",
            session_id="abc",
            data={
                "elapsed_ms": 200_000,
                "last_tool_name": "Bash",
                "worktree_root": "/tmp/proj",
            },
        )
    )
    assert sent == []  # topic empty


@pytest.mark.asyncio
async def test_dispatcher_posts_when_topic_set(db, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_topic(db, "csm-test-topic")

    sent: list[dict] = []

    async def fake_post(self, url, content=None, headers=None, timeout=None):
        sent.append({"url": url, "content": content, "headers": headers})

        class R:
            def raise_for_status(self_inner):
                return None

        return R()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    dispatcher = NtfyDispatcher(db)
    dispatcher._client = httpx.AsyncClient()
    try:
        await dispatcher._dispatch(
            BusEvent(
                kind="hang",
                session_id="abc",
                data={
                    "elapsed_ms": 200_000,
                    "last_tool_name": "Bash",
                    "worktree_root": "/tmp/proj-a",
                },
            )
        )
    finally:
        await dispatcher._client.aclose()

    assert len(sent) == 1
    assert sent[0]["url"].endswith("/csm-test-topic")
    assert sent[0]["headers"]["Priority"] == "5"
    assert "[proj-a] hung" in sent[0]["headers"]["Title"]


# ────────── send_test_notification ──────────


@pytest.mark.asyncio
async def test_test_notification_no_topic_returns_false() -> None:
    assert (await send_test_notification("")) is False


@pytest.mark.asyncio
async def test_test_notification_posts_when_topic_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict] = []

    async def fake_post(self, url, content=None, headers=None, timeout=None):
        sent.append({"url": url, "content": content, "headers": headers})

        class R:
            def raise_for_status(self_inner):
                return None

        return R()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    delivered = await send_test_notification("csm-x")
    assert delivered is True
    assert len(sent) == 1
    assert sent[0]["url"].endswith("/csm-x")


# ────────── format helpers ──────────


def test_format_elapsed() -> None:
    assert ntfy._format_elapsed(45_000) == "45s"
    assert ntfy._format_elapsed(120_000) == "2m"
    assert ntfy._format_elapsed(3_900_000) == "1h5m"
