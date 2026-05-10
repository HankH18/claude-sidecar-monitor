"""HTTP-level tests for the hook receiver."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from csm.db import connect
from csm.server import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Boot a FastAPI app with an isolated DB."""
    app = create_app()

    # Replace the lifespan-managed connection with our temp one.
    db = connect(db_path=tmp_path / "store.db")
    app.state.db = db
    # Disable the lifespan that would re-open the DB on startup.
    app.router.lifespan_context = lambda _app: _no_op_lifespan()  # type: ignore[assignment]

    with TestClient(app) as c:
        yield c
    db.close()


from contextlib import asynccontextmanager  # noqa: E402  -- used by fixture


@asynccontextmanager
async def _no_op_lifespan():
    yield


def test_unknown_event_returns_400(client: TestClient) -> None:
    response = client.post(
        "/hook/SomethingMadeUp",
        json={"session_id": "x", "cwd": "/tmp"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"]["code"] == "unknown_event"


def test_known_event_returns_empty_object(client: TestClient) -> None:
    response = client.post(
        "/hook/SessionStart",
        json={
            "session_id": "abc-123",
            "cwd": "/tmp/proj",
            "transcript_path": "/tmp/.claude/projects/proj/abc-123.jsonl",
            "source": "startup",
        },
    )
    assert response.status_code == 200
    assert response.json() == {}


def test_missing_session_id_returns_400(client: TestClient) -> None:
    response = client.post("/hook/SessionStart", json={"cwd": "/tmp"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_payload"


def test_full_session_lifecycle_via_http(client: TestClient) -> None:
    """End-to-end: SessionStart → PreToolUse → PostToolUse → Stop."""
    sid = "lifecycle-test-001"
    base = {"session_id": sid, "cwd": "/tmp/proj", "transcript_path": "/tmp/x.jsonl"}

    assert client.post("/hook/SessionStart", json={**base, "source": "startup"}).status_code == 200
    assert (
        client.post(
            "/hook/PreToolUse",
            json={**base, "tool_name": "Bash", "tool_use_id": "t1"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/hook/PostToolUse",
            json={**base, "tool_name": "Bash", "tool_use_id": "t1"},
        ).status_code
        == 200
    )
    assert client.post("/hook/Stop", json=base).status_code == 200

    db = client.app.state.db  # type: ignore[attr-defined]
    state = db.execute(
        "SELECT state, last_event_name FROM sessions WHERE session_id=?", (sid,)
    ).fetchone()
    assert state[0] == "done"
    assert state[1] == "Stop"

    events = db.execute("SELECT count(*) FROM events WHERE session_id=?", (sid,)).fetchone()[0]
    assert events == 4
