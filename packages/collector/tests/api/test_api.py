"""Integration tests for the REST + SSE API (T11)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from csm import __version__
from csm.api import router as api_router
from csm.bus import BusEvent, bus
from csm.db import connect
from csm.hooks import router as hooks_router


@asynccontextmanager
async def _no_op_lifespan(_app):
    yield


def _now_minus(seconds: int) -> str:
    return (datetime.now(tz=UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    """Build a FastAPI app with the API + hooks routers and a temp DB."""
    a = FastAPI(version=__version__, lifespan=_no_op_lifespan)
    a.include_router(api_router)
    a.include_router(hooks_router)
    a.state.db = connect(db_path=tmp_path / "store.db")

    # Seed a couple of sessions + transcript messages.
    db = a.state.db
    db.execute(
        """
        INSERT INTO sessions (
            session_id, worktree_root, project_label, cwd, agent_type,
            state, last_event_at, last_event_name, started_at, primary_model,
            input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "alpha",
            "/tmp/proj-a",
            "proj-a",
            "/tmp/proj-a",
            "coordinator",
            "running",
            _now_minus(10),
            "PreToolUse",
            _now_minus(120),
            "claude-opus-4-7",
            500,
            1000,
            200,
            100,
        ),
    )
    db.execute(
        """
        INSERT INTO sessions (
            session_id, worktree_root, project_label, cwd, parent_session_id,
            state, last_event_at, started_at, primary_model,
            input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "beta",
            "/tmp/proj-a",
            "proj-a",
            "/tmp/proj-a",
            "alpha",
            "done",
            _now_minus(5),
            _now_minus(60),
            "claude-opus-4-7",
            300,
            600,
            50,
            25,
        ),
    )
    db.execute(
        """
        INSERT INTO transcript_messages (
            session_id, role, timestamp, content_json, model,
            input_tokens, output_tokens,
            cache_creation_input_tokens, cache_read_input_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "alpha",
            "assistant",
            _now_minus(60),
            "{}",
            "claude-opus-4-7",
            500,
            1000,
            100,
            200,
        ),
    )

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    app.state.db.close()


# ────────── /api/state ──────────


def test_get_state(client: TestClient) -> None:
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    sids = {s["session_id"] for s in body["sessions"]}
    assert {"alpha", "beta"} <= sids
    assert "hang_yellow_ms" in body["settings"]


# ────────── /api/sessions ──────────


def test_get_session_detail(client: TestClient) -> None:
    r = client.get("/api/sessions/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "alpha"
    assert body["input_tokens"] == 500
    assert body["output_tokens"] == 1000
    assert isinstance(body["by_model"], list)
    assert body["by_model"][0]["model"] == "claude-opus-4-7"


def test_get_session_detail_404_for_missing(client: TestClient) -> None:
    r = client.get("/api/sessions/no-such-id")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "session_not_found"


def test_get_transcript_paginated(client: TestClient) -> None:
    r = client.get("/api/sessions/alpha/transcript")
    assert r.status_code == 200
    body = r.json()
    assert body["messages"][0]["session_id"] == "alpha"
    assert body["messages"][0]["model"] == "claude-opus-4-7"


# ────────── /api/tree ──────────


def test_get_tree(client: TestClient) -> None:
    r = client.get("/api/tree?worktree=/tmp/proj-a")
    assert r.status_code == 200
    nodes = r.json()
    # Tree is rooted at parent-less sessions; alpha has a child (beta).
    assert any(n["session"]["session_id"] == "alpha" for n in nodes)
    alpha = next(n for n in nodes if n["session"]["session_id"] == "alpha")
    assert any(c["session"]["session_id"] == "beta" for c in alpha["children"])
    # Subtree rollup includes both alpha + beta tokens.
    assert alpha["subtree_tokens"]["input"] == 800  # 500 + 300
    assert alpha["subtree_tokens"]["output"] == 1600
    assert alpha["subtree_tokens"]["descendant_count"] == 1
    # Tree node Session payloads must carry full identifying fields — the
    # dashboard's ProjectDetail links against worktree_root / project_label /
    # parent_session_id, and the page header shows the project label.
    assert alpha["session"]["worktree_root"] == "/tmp/proj-a"
    assert alpha["session"]["project_label"] == "proj-a"
    assert alpha["session"]["parent_session_id"] is None
    beta = next(c for c in alpha["children"] if c["session"]["session_id"] == "beta")
    assert beta["session"]["worktree_root"] == "/tmp/proj-a"
    assert beta["session"]["parent_session_id"] == "alpha"


def test_get_tree_empty_for_unknown_worktree(client: TestClient) -> None:
    r = client.get("/api/tree?worktree=/no/such")
    assert r.status_code == 200
    assert r.json() == []


# ────────── /api/dashboard (V3 KPI rollup) ──────────


def test_get_dashboard_shape(client: TestClient) -> None:
    """V3 — the dashboard endpoint returns the full KPI rollup with
    state counts, token totals, event-rate sparkline, and top models."""
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    # Top-line counts.
    assert "live_sessions" in body
    assert "hung_sessions" in body
    assert "state_counts" in body
    # State counts include every state column with an int.
    for key in ("running", "tool", "waiting_user", "idle", "hung", "done"):
        assert key in body["state_counts"]
        assert isinstance(body["state_counts"][key], int)
    # Token totals are scoped to a trailing window.
    assert isinstance(body["total_tokens_today"], int)
    assert isinstance(body["total_tokens_last_hour"], int)
    # Sparkline always returns the fixed bucket count, zero-filled.
    assert isinstance(body["events_per_minute_60m"], list)
    assert len(body["events_per_minute_60m"]) == 60
    for bucket in body["events_per_minute_60m"]:
        assert "ts" in bucket
        assert "count" in bucket
        assert isinstance(bucket["count"], int)
    # Top models is a list (may be empty in the test fixture).
    assert isinstance(body["top_models_today"], list)
    # As-of timestamp lets the client flag stale data.
    assert body["as_of"]


def test_get_dashboard_live_count_matches_state_counts(client: TestClient) -> None:
    """live_sessions = sum of non-done state buckets. Regression guard
    against `state_counts.done` accidentally being included."""
    r = client.get("/api/dashboard")
    body = r.json()
    sc = body["state_counts"]
    expected_live = sc["running"] + sc["tool"] + sc["waiting_user"] + sc["idle"] + sc["hung"]
    assert body["live_sessions"] == expected_live
    assert body["hung_sessions"] == sc["hung"]


# ────────── /api/state — V3 session fields ──────────


def test_state_includes_tokens_last_hour_field(client: TestClient) -> None:
    """V3 — every Session returned from /api/state carries tokens_last_hour
    (int when transcript rows exist in window, None otherwise)."""
    r = client.get("/api/state")
    body = r.json()
    assert body["sessions"], "fixture should seed at least one session"
    for s in body["sessions"]:
        assert "tokens_last_hour" in s
        v = s["tokens_last_hour"]
        assert v is None or isinstance(v, int)


# ────────── /api/tokens ──────────


def test_get_tokens(client: TestClient) -> None:
    r = client.get("/api/tokens")
    assert r.status_code == 200
    body = r.json()
    assert "topSessions" in body
    assert "topProjects" in body
    assert "totalsByModel" in body
    assert "dailyTotals" in body
    # Project with both sessions should rank top.
    assert body["topProjects"][0]["worktree_root"] == "/tmp/proj-a"
    assert body["topProjects"][0]["session_count"] == 2


# ────────── /api/settings ──────────


def test_get_settings(client: TestClient) -> None:
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["hang_yellow_ms"] == 60000
    assert body["hang_red_ms"] == 180000
    assert body["ntfy_topic"] == ""
    assert "plan_seat_type" not in body  # spec amendment


def test_patch_settings_round_trip(client: TestClient) -> None:
    r = client.patch("/api/settings", json={"ntfy_topic": "csm-test-topic"})
    assert r.status_code == 200
    assert r.json()["ntfy_topic"] == "csm-test-topic"

    r = client.get("/api/settings")
    assert r.json()["ntfy_topic"] == "csm-test-topic"


def test_patch_settings_partial(client: TestClient) -> None:
    r = client.patch("/api/settings", json={"hang_yellow_ms": 90000})
    assert r.status_code == 200
    assert r.json()["hang_yellow_ms"] == 90000
    assert r.json()["hang_red_ms"] == 180000  # unchanged


def test_patch_settings_extended_approval_keys(client: TestClient) -> None:
    """V2.D4 — PATCH /api/settings round-trips the new approval keys
    (approval_enabled / approval_tools / approval_timeout_ms /
    dashboard_url) and serialises booleans as '0'/'1' so the dashboard
    sees a real bool on the way back."""
    r = client.patch(
        "/api/settings",
        json={
            "approval_enabled": True,
            "approval_tools": "Bash, Edit, Write",
            "approval_timeout_ms": 45_000,
            "dashboard_url": "https://csm.tail-scale.ts.net",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["approval_enabled"] is True
    assert body["approval_tools"] == "Bash, Edit, Write"
    assert body["approval_timeout_ms"] == 45_000
    assert body["dashboard_url"] == "https://csm.tail-scale.ts.net"

    # Re-read to confirm persistence; existing v1 keys must remain stable.
    g = client.get("/api/settings")
    body2 = g.json()
    assert body2["approval_enabled"] is True
    assert body2["dashboard_url"] == "https://csm.tail-scale.ts.net"
    assert body2["hang_yellow_ms"] == 60000  # unchanged from default

    # Flip approval_enabled off and confirm bool serialisation round-trips.
    r2 = client.patch("/api/settings", json={"approval_enabled": False})
    assert r2.status_code == 200
    assert r2.json()["approval_enabled"] is False


@pytest.mark.asyncio
async def test_patch_settings_emits_settings_changed_event(app: FastAPI) -> None:
    """PATCH /api/settings must publish a `settings_changed` BusEvent so the
    dashboard's useSettings hook picks up the new thresholds live."""
    queue = await bus.subscribe()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.patch("/api/settings", json={"ntfy_topic": "csm-new"})
        assert r.status_code == 200
        # Drain the bus until we see settings_changed (other events may have
        # been published since fixture setup).
        evt = None
        for _ in range(8):
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                break
            if evt.kind == "settings_changed":
                break
        assert evt is not None
        assert evt.kind == "settings_changed"
        assert evt.data["ntfy_topic"] == "csm-new"
    finally:
        await bus.unsubscribe(queue)


# ────────── /stream (SSE) ──────────


@pytest.mark.skip(reason="SSE-via-ASGITransport hangs in pytest; manual verify works fine")
@pytest.mark.asyncio
async def test_stream_delivers_bus_events(app: FastAPI) -> None:
    """Subscribe to /stream via ASGI transport, push a BusEvent, assert receipt.

    Using TestClient.stream() blocks the test thread; httpx.AsyncClient
    against the ASGI transport gives us a real async iterator.
    """
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client_,
        client_.stream("GET", "/stream") as response,
    ):
        assert response.status_code == 200

        async def push_after_a_moment() -> None:
            await asyncio.sleep(0.05)
            await bus.publish(
                BusEvent(
                    kind="session_update",
                    session_id="alpha",
                    data={"state": "tool", "session_id": "alpha"},
                )
            )

        push_task = asyncio.create_task(push_after_a_moment())
        try:
            seen = False
            async for raw_line in response.aiter_lines():
                if not raw_line.startswith("data:"):
                    continue
                payload = raw_line[len("data:") :].strip()
                if not payload or payload == "{}":
                    continue
                body = json.loads(payload)
                if body.get("kind") == "session_update":
                    assert body["session_id"] == "alpha"
                    seen = True
                    break
            assert seen, "expected to receive a session_update SSE event"
        finally:
            push_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await push_task
