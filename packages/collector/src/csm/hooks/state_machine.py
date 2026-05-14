"""Hook event → session state transition logic.

The single ``apply_event`` entry point handles every Claude Code hook
event and returns the post-transition session row. It also writes to
``events`` and emits a ``BusEvent`` describing the change.

State machine per docs/spec.md §4.1:

    SessionStart        → running
    UserPromptSubmit    → running (bumps last_event_at)
    PreToolUse          → tool   (records last_tool_name)
    PostToolUse         → running (clears last_tool_name)
    Notification        → waiting_user (only if permission_request)
    PreCompact          → unchanged
    Stop / SessionEnd   → done
    SubagentStop        → done
    PermissionRequest   → waiting_user
    Setup               → unchanged

Unknown events raise :class:`UnknownEventError`. The receiver translates
that to HTTP 400.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from csm.bus import BusEvent, bus
from csm.hooks.worktree import project_label, resolve_worktree

KNOWN_EVENTS: frozenset[str] = frozenset(
    {
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
    }
)

# State machine targets per event. ``None`` means "leave state alone".
_TRANSITIONS: dict[str, str | None] = {
    "SessionStart": "running",
    "UserPromptSubmit": "running",
    "PreToolUse": "tool",
    "PostToolUse": "running",
    "Notification": None,  # conditional — see logic below
    "Stop": "done",
    "SubagentStop": "done",
    "SessionEnd": "done",
    "PreCompact": None,
    "Setup": None,
    "PermissionRequest": "waiting_user",
}


class UnknownEventError(ValueError):
    """Raised when the event name isn't in :data:`KNOWN_EVENTS`."""


@dataclass(frozen=True)
class SessionSnapshot:
    """Compact view of a sessions row for ``BusEvent.data`` payloads."""

    session_id: str
    state: str
    last_event_at: str
    last_event_name: str | None
    last_tool_name: str | None
    worktree_root: str
    parent_session_id: str | None


def utcnow_iso() -> str:
    """ISO 8601 UTC timestamp, second precision (matches schema text columns)."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def apply_event(
    conn: Any,
    event_name: str,
    payload: dict[str, Any],
    *,
    received_at: str | None = None,
) -> SessionSnapshot:
    """Apply a hook event to the database and emit on the bus.

    Returns a :class:`SessionSnapshot` of the post-transition session row.

    Raises :class:`UnknownEventError` if ``event_name`` isn't recognised.
    """
    if event_name not in KNOWN_EVENTS:
        raise UnknownEventError(event_name)

    received_at = received_at or utcnow_iso()
    session_id = payload.get("session_id")
    if not session_id:
        # Some hook events (e.g. Setup) may legitimately lack session_id;
        # for now we require one. The receiver will translate this into
        # a 400 with a clear error.
        raise ValueError("payload missing session_id")

    # Wrap the multi-statement DB work in BEGIN IMMEDIATE/COMMIT so the
    # session-row snapshot we read at the end reflects only our own writes
    # — the hang scanner can't flip the row between our UPDATE and our
    # SELECT (and thus can't make us emit a session_update that says
    # state='hung' when we just wrote state='running'). BEGIN IMMEDIATE
    # acquires the SQLite write lock up front so two concurrent receivers
    # serialise cleanly rather than fighting at COMMIT time.
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Ensure a row exists (SessionStart creates, others upsert minimal).
        _ensure_session(conn, session_id, payload, received_at)

        new_state = _resolve_target_state(event_name, payload, conn, session_id)
        tool_name = payload.get("tool_name")
        tool_use_id = payload.get("tool_use_id")
        duration_ms = _resolve_duration_ms(payload)

        # Record the event in `events`.
        conn.execute(
            """
            INSERT INTO events (
                session_id, event_name, received_at, tool_name, tool_use_id,
                duration_ms, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event_name,
                received_at,
                tool_name,
                tool_use_id,
                duration_ms,
                json.dumps(payload, default=str),
            ),
        )

        # Update the sessions row.
        last_tool = _resolve_last_tool(event_name, tool_name, conn, session_id)
        conn.execute(
            """
            UPDATE sessions
            SET state           = COALESCE(?, state),
                last_event_at   = ?,
                last_event_name = ?,
                last_tool_name  = ?,
                completed_at    = COALESCE(completed_at,
                                           CASE WHEN ? IN ('done') THEN ? ELSE NULL END)
            WHERE session_id = ?
            """,
            (
                new_state,
                received_at,
                event_name,
                last_tool,
                new_state,
                received_at,
                session_id,
            ),
        )

        # Tree linkage (T10): resolve parent for fresh sessions. The lookup
        # walks events for a recent ``Task`` PreToolUse in the same
        # worktree; see csm.tree.resolve_parent.
        if event_name == "SessionStart":
            from csm.tree import resolve_parent

            resolve_parent(conn, str(session_id))

            # V2.A2 — assign the deterministic nickname (idempotent via
            # COALESCE; same session_id → same nickname forever).
            from csm.identity import generate_nickname

            conn.execute(
                "UPDATE sessions SET nickname = COALESCE(nickname, ?) WHERE session_id = ?",
                (generate_nickname(str(session_id)), str(session_id)),
            )

        # V2.A2 — derive a short title from the first user prompt. Only
        # writes when title_source IS NULL so a subsequent
        # UserPromptSubmit (mid-session continuation) doesn't clobber
        # the original intent.
        if event_name == "UserPromptSubmit":
            from csm.identity import derive_title_from_user_prompt

            prompt_text = payload.get("prompt")
            if isinstance(prompt_text, str):
                title = derive_title_from_user_prompt(prompt_text)
                if title is not None:
                    conn.execute(
                        "UPDATE sessions SET title = ?, title_source = 'user_prompt' "
                        "WHERE session_id = ? AND title_source IS NULL",
                        (title, str(session_id)),
                    )

        # V2.C2 — synthesise / close virtual subagent rows for in-session
        # Agent tool calls. Tool name is "Agent" (NOT "Task" as the v1
        # spec assumed — confirmed empirically). On PreToolUse insert a
        # pending virtual; on PostToolUse mark it done. Token attribution
        # is deferred to v2.1 — Agent sub-runs are server-side at
        # Anthropic so no separate JSONL exists to attribute against.
        virtual_emit: dict[str, Any] | None = None
        if event_name in ("PreToolUse", "PostToolUse") and tool_name == "Agent":
            virtual_emit = _apply_agent_tool_event(
                conn,
                event_name=event_name,
                parent_session_id=str(session_id),
                tool_use_id=str(tool_use_id) if tool_use_id else "",
                tool_input=payload.get("tool_input") or {},
                received_at=received_at,
            )

        snapshot = _snapshot(conn, session_id)
        conn.execute("COMMIT")
    except Exception:
        with contextlib.suppress(Exception):
            conn.execute("ROLLBACK")
        raise

    # Emit AFTER commit so SSE subscribers see a state that's actually
    # persisted, never a doomed-rollback view.
    _emit(snapshot, event_name, received_at)
    if virtual_emit is not None:
        _emit_virtual(virtual_emit)

    # V2.B — recompute the session's activity digest. We do this outside
    # the state-machine transaction (autocommit connection) so the
    # digest write doesn't extend the receiver's write lock; the digest
    # is derived data and a missed update is at worst a one-event stale
    # SSE message (the next event will catch it).
    _maybe_emit_digest(conn, str(session_id))

    return snapshot


def _apply_agent_tool_event(
    conn: Any,
    *,
    event_name: str,
    parent_session_id: str,
    tool_use_id: str,
    tool_input: dict[str, Any],
    received_at: str,
) -> dict[str, Any] | None:
    """V2.C2: maintain a row in ``subagent_sessions`` for each Agent tool
    call. Returns a dict suitable for ``_emit_virtual``, or None when we
    can't form a sane row (missing tool_use_id).

    PreToolUse with tool_name="Agent":
        INSERT OR IGNORE — first Pre fires, dupes are no-ops.

    PostToolUse with tool_name="Agent":
        UPDATE state='done', completed_at=<received_at>.
    """
    if not tool_use_id:
        return None
    from csm.identity import _truncate_at_word, infer_agent_kind

    virtual_id = f"{parent_session_id}:{tool_use_id}"

    if event_name == "PreToolUse":
        description = tool_input.get("description") if isinstance(tool_input, dict) else None
        prompt = tool_input.get("prompt") if isinstance(tool_input, dict) else None
        subagent_type = tool_input.get("subagent_type") if isinstance(tool_input, dict) else None
        kind_res = infer_agent_kind(tool_input if isinstance(tool_input, dict) else {})
        kind = kind_res.kind if kind_res else None
        title: str | None = None
        if isinstance(description, str) and description.strip():
            title = _truncate_at_word(description.strip(), 80)
        conn.execute(
            """
            INSERT OR IGNORE INTO subagent_sessions (
                virtual_id, parent_session_id, tool_use_id,
                title, description, prompt, agent_kind, subagent_type,
                state, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                virtual_id,
                parent_session_id,
                tool_use_id,
                title,
                description if isinstance(description, str) else None,
                prompt if isinstance(prompt, str) else None,
                kind,
                subagent_type if isinstance(subagent_type, str) else None,
                received_at,
            ),
        )
        return {
            "virtual_id": virtual_id,
            "parent_session_id": parent_session_id,
            "title": title,
            "description": description,
            "agent_kind": kind,
            "subagent_type": subagent_type,
            "state": "running",
            "started_at": received_at,
            "completed_at": None,
        }

    # PostToolUse — close out
    conn.execute(
        "UPDATE subagent_sessions SET state = 'done', completed_at = ? "
        "WHERE virtual_id = ? AND state = 'running'",
        (received_at, virtual_id),
    )
    return {
        "virtual_id": virtual_id,
        "parent_session_id": parent_session_id,
        "state": "done",
        "completed_at": received_at,
    }


def _emit_virtual(payload: dict[str, Any]) -> None:
    """Schedule a ``subagent_update`` bus publish from this thread.

    Uses ``bus.main_loop`` (captured at lifespan startup) because we're
    invoked from ``asyncio.to_thread`` workers in production — those
    threads have no running loop of their own, so
    ``asyncio.get_running_loop()`` raises ``RuntimeError``. Falls back
    to a best-effort ``get_running_loop`` when ``main_loop`` is unset
    (e.g. unit tests that drive ``apply_event`` synchronously).
    """
    import asyncio

    loop = bus.main_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
    event = BusEvent(
        kind="subagent_update",
        session_id=payload.get("parent_session_id"),
        data=payload,
    )
    asyncio.run_coroutine_threadsafe(bus.publish(event), loop)


def _maybe_emit_digest(conn: Any, session_id: str) -> None:
    """V2.B — recompute and publish session_digest_update when the
    derived activity summary actually changes.

    Best-effort: any failure is swallowed so a digest hiccup never
    breaks the receiver. The next event for this session re-derives.
    """
    try:
        from csm.digest import apply_digest_update

        summary, generated_at, changed = apply_digest_update(conn, session_id)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("digest recompute failed for session %s", session_id)
        return
    if not changed:
        return

    import asyncio

    loop = bus.main_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
    bus_event = BusEvent(
        kind="session_digest_update",
        session_id=session_id,
        data={
            "session_id": session_id,
            "activity_summary": summary,
            "activity_updated_at": generated_at,
        },
    )
    asyncio.run_coroutine_threadsafe(bus.publish(bus_event), loop)


# ────────────────────────── helpers ──────────────────────────


def _ensure_session(conn: Any, session_id: str, payload: dict[str, Any], received_at: str) -> None:
    """Insert a minimal sessions row if one doesn't exist."""
    cwd = payload.get("cwd") or ""
    worktree = resolve_worktree(cwd) if cwd else ""
    label = project_label(worktree) if worktree else None
    transcript_path = payload.get("transcript_path")
    conn.execute(
        """
        INSERT OR IGNORE INTO sessions (
            session_id, worktree_root, project_label, cwd,
            transcript_path, last_event_at, started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, worktree, label, cwd, transcript_path, received_at, received_at),
    )
    # Update transcript_path / cwd / worktree_root if they were missing
    # before but the new payload has them (e.g. SessionStart arrived
    # after a tool-use event due to clock skew).
    if cwd or transcript_path:
        conn.execute(
            """
            UPDATE sessions
            SET cwd             = COALESCE(NULLIF(cwd, ''), ?),
                transcript_path = COALESCE(transcript_path, ?),
                worktree_root   = COALESCE(NULLIF(worktree_root, ''), ?),
                project_label   = COALESCE(project_label, ?)
            WHERE session_id = ?
            """,
            (cwd, transcript_path, worktree, label, session_id),
        )


def _resolve_target_state(
    event_name: str, payload: dict[str, Any], conn: Any, session_id: str
) -> str | None:
    """Return the new ``state`` value, or ``None`` to leave unchanged."""
    if event_name == "Notification":
        # Only permission requests transition to waiting_user.
        if payload.get("notification_type") == "permission_request":
            return "waiting_user"
        return None

    if event_name == "PostToolUse":
        # Only return to running if we were in tool — don't override
        # done/hung accidentally.
        cur = conn.execute(
            "SELECT state FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if cur and cur[0] == "tool":
            return "running"
        return None

    return _TRANSITIONS.get(event_name)


def _resolve_last_tool(
    event_name: str, tool_name: str | None, conn: Any, session_id: str
) -> str | None:
    """Compute the last_tool_name to write back."""
    if event_name == "PreToolUse":
        return tool_name
    if event_name == "PostToolUse":
        return None  # clear it
    # For other events leave as-is.
    cur = conn.execute(
        "SELECT last_tool_name FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    return cur[0] if cur else None


def _resolve_duration_ms(payload: dict[str, Any]) -> int | None:
    """Pull duration_ms from common payload shapes (best-effort)."""
    for key in ("duration_ms", "durationMs", "elapsed_ms"):
        v = payload.get(key)
        if isinstance(v, int):
            return v
    response = payload.get("tool_response")
    if isinstance(response, dict):
        for key in ("duration_ms", "durationMs"):
            v = response.get(key)
            if isinstance(v, int):
                return v
    return None


def _snapshot(conn: Any, session_id: str) -> SessionSnapshot:
    row = conn.execute(
        """
        SELECT state, last_event_at, last_event_name, last_tool_name,
               worktree_root, parent_session_id
        FROM sessions WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"session {session_id!r} disappeared mid-transition")
    return SessionSnapshot(
        session_id=session_id,
        state=row[0],
        last_event_at=row[1],
        last_event_name=row[2],
        last_tool_name=row[3],
        worktree_root=row[4],
        parent_session_id=row[5],
    )


def _emit(snapshot: SessionSnapshot, event_name: str, received_at: str) -> None:
    """Schedule a bus publish without blocking the receiver thread.

    The bus is asyncio-based; the receiver runs in a worker thread (via
    FastAPI's threadpool). ``asyncio.run_coroutine_threadsafe`` is the
    bridge — but in tests we may not have a running loop, so we degrade
    silently in that case.
    """
    import asyncio

    payload = {
        "session_id": snapshot.session_id,
        "state": snapshot.state,
        "last_event_at": snapshot.last_event_at,
        "last_event_name": snapshot.last_event_name,
        "last_tool_name": snapshot.last_tool_name,
        "worktree_root": snapshot.worktree_root,
        "parent_session_id": snapshot.parent_session_id,
        "event_name": event_name,
        "received_at": received_at,
    }
    bus_event = BusEvent(
        kind="session_update",
        session_id=snapshot.session_id,
        data=payload,
    )
    loop = bus.main_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop — caller is sync (test path); skip emission
    fut = asyncio.run_coroutine_threadsafe(bus.publish(bus_event), loop)
    # Surface bus-publish failures in the log instead of dropping silently.
    # The future is "free-running" but we attach a done callback that
    # raises into a logger if it errors. Cancelled is benign.
    import logging
    from concurrent.futures import Future

    def _check(f: Future[Any]) -> None:
        try:
            exc = f.exception(timeout=0)
        except Exception:
            return
        if exc is not None:
            logging.getLogger(__name__).warning(
                "bus publish for session %s raised: %r", snapshot.session_id, exc
            )

    fut.add_done_callback(_check)
