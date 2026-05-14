"""Phone-side permission approval (V2.D).

The flow:

1. The hook receiver sees a ``PreToolUse`` for a session that has
   approval enabled AND a tool name in the configured set. It calls
   :func:`request_decision`.
2. ``request_decision`` inserts a ``pending`` row in
   ``permission_requests``, fires an ntfy push to the user, emits a
   ``permission_request`` BusEvent, and awaits an asyncio Event for at
   most ``approval_timeout_ms``.
3. The user taps the push or sees the dashboard banner, opens the
   modal, hits Allow / Deny / Ask. The dashboard calls
   ``POST /api/permission-requests/:id/decide`` which invokes
   :func:`record_decision` — that UPDATEs the row and sets the Event.
4. ``request_decision`` returns the decision dict to the receiver,
   which returns it as the hook response body. Claude Code reads the
   ``permissionDecision`` field and proceeds accordingly.

On timeout the row is marked ``timed_out`` and the receiver returns
``{}`` (fail-open). If the collector restarts mid-pending, the
``cleanup_stale_pending`` helper marks all stale rows ``timed_out``
on startup so the dashboard's pending count is honest.

Audit: every decision is logged to ``permission_requests`` and the
``events`` table records the original ``PreToolUse``. No passphrases
or keys are logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from csm.bus import BusEvent, bus

log = logging.getLogger(__name__)

__all__ = [
    "PendingDecisions",
    "cleanup_stale_pending",
    "decisions",
    "is_tool_approval_required",
    "load_approval_config",
    "record_decision",
    "request_decision",
]


@dataclass(frozen=True)
class ApprovalConfig:
    enabled: bool
    tools: frozenset[str]
    timeout_ms: int


@dataclass(frozen=True)
class DecisionResult:
    """What ``request_decision`` returns. Matches the Claude Code hook
    response shape (``permissionDecision`` + ``permissionDecisionReason``)
    or an empty dict on timeout / disabled-fast-path."""

    decision: str | None  # 'allow' | 'deny' | 'ask' | None
    reason: str | None

    def to_hook_response(self) -> dict[str, Any]:
        if self.decision is None:
            return {}
        out: dict[str, Any] = {"permissionDecision": self.decision}
        if self.reason:
            out["permissionDecisionReason"] = self.reason
        return out


class PendingDecisions:
    """In-process registry: ``request_id`` → asyncio.Event + holder.

    The receiver awaits the Event; ``record_decision`` sets it. Both
    sides agree on the request_id (the INTEGER PRIMARY KEY autoincrement
    from the ``permission_requests`` table).

    There's a real race between the receiver's INSERT (which commits in
    autocommit mode and immediately makes the row visible to the
    dashboard) and the subsequent ``register()`` call that creates the
    waiter. If the dashboard decides in that window, ``deliver()`` would
    arrive at an empty map and the receiver would time out despite a
    real decision existing. We close the race by stashing the decision
    in ``_deferred`` whenever it arrives before its waiter; ``register``
    immediately consumes any matching deferred entry and pre-sets the
    Event so the awaiter wakes up on first ``await``.
    """

    def __init__(self) -> None:
        self._holders: dict[int, dict[str, Any]] = {}
        # Decisions that arrived before a waiter registered; consumed
        # on the next ``register(request_id)`` call.
        self._deferred: dict[int, tuple[str, str | None]] = {}
        self._lock = asyncio.Lock()

    async def register(self, request_id: int) -> asyncio.Event:
        event = asyncio.Event()
        async with self._lock:
            deferred = self._deferred.pop(request_id, None)
            if deferred is not None:
                decision, reason = deferred
                self._holders[request_id] = {
                    "event": event,
                    "decision": decision,
                    "reason": reason,
                }
                event.set()
            else:
                self._holders[request_id] = {
                    "event": event,
                    "decision": None,
                    "reason": None,
                }
        return event

    async def deliver(self, request_id: int, decision: str, reason: str | None) -> bool:
        """Deliver a decision to its waiter.

        If a waiter is registered, populate its holder and set the
        Event. If no waiter is registered yet, stash the decision in
        ``_deferred`` so the next ``register()`` call can pick it up
        immediately — this closes the INSERT-then-register race.

        Returns True in both cases (the decision was accepted by the
        registry). The previous semantics returned False on "no waiter"
        but callers ignored the boolean, and conflating "no waiter" with
        "delivery failed" was the bug being fixed.
        """
        async with self._lock:
            holder = self._holders.get(request_id)
            if holder is None:
                # No waiter yet — stash for whoever registers next.
                self._deferred[request_id] = (decision, reason)
                return True
            holder["decision"] = decision
            holder["reason"] = reason
            holder["event"].set()
            return True

    async def collect(self, request_id: int) -> tuple[str | None, str | None]:
        """After ``event.wait()`` returns, fetch the decision + reason
        and clear the registration. Always call from the same task that
        invoked register()."""
        async with self._lock:
            holder = self._holders.pop(request_id, None)
        if holder is None:
            return None, None
        return holder["decision"], holder["reason"]

    async def cancel(self, request_id: int) -> None:
        """Drop the registration on timeout/cancel — no waiter pending
        anymore. Also drops any deferred entry that nobody will ever
        come collect."""
        async with self._lock:
            self._holders.pop(request_id, None)
            self._deferred.pop(request_id, None)


# Module-level singleton. One per process. The collector daemon lives
# in one process so this is safe; if we ever go multi-process we'll
# need a different signalling channel (Redis pub/sub, fcntl flock, etc.).
decisions = PendingDecisions()

# Strong refs for free-running cleanup tasks spawned by ``request_decision``
# on the cancellation path. Python's asyncio loop holds tasks only via
# a weakref; without a strong ref the task can be GC'd before it
# updates the DB row. Tasks remove themselves on completion.
_CLEANUP_TASKS: set[asyncio.Task[None]] = set()


def _register_cleanup_task(task: asyncio.Task[None]) -> None:
    _CLEANUP_TASKS.add(task)
    task.add_done_callback(_CLEANUP_TASKS.discard)


# ──────────────────────────── config ────────────────────────────


def load_approval_config(conn: Any) -> ApprovalConfig:
    """Read approval settings from the DB. Pure-sync."""
    rows = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    tools_csv = rows.get("approval_tools", "")
    tools = frozenset(t.strip() for t in tools_csv.split(",") if t.strip())
    return ApprovalConfig(
        enabled=rows.get("approval_enabled", "0") == "1",
        tools=tools,
        timeout_ms=int(rows.get("approval_timeout_ms", "60000")),
    )


def is_tool_approval_required(conn: Any, tool_name: str | None) -> ApprovalConfig | None:
    """Return the config IF approval applies to this tool, else None.
    Fast-pathed for the receiver's hot loop — single SELECT."""
    if not tool_name:
        return None
    config = load_approval_config(conn)
    if not config.enabled:
        return None
    if tool_name not in config.tools:
        return None
    return config


# ──────────────────────────── flow ────────────────────────────


async def request_decision(
    conn: Any,
    *,
    session_id: str,
    tool_use_id: str | None,
    tool_name: str,
    tool_input: Any,
    timeout_ms: int,
) -> DecisionResult:
    """Insert a pending row, fire the ntfy push + bus event, await a
    decision. Returns the user's choice or an empty result on timeout."""
    requested_at = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    tool_input_json = json.dumps(tool_input, default=str)

    def _insert() -> int:
        cursor = conn.execute(
            """
            INSERT INTO permission_requests (
                session_id, tool_use_id, tool_name, tool_input_json,
                status, requested_at
            ) VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (session_id, tool_use_id, tool_name, tool_input_json, requested_at),
        )
        return int(cursor.lastrowid or 0)

    request_id = await asyncio.to_thread(_insert)
    if request_id <= 0:
        log.warning("permission_requests: failed to insert pending row")
        return DecisionResult(decision=None, reason=None)

    # From this point on we own a row in the DB and (after register()) a
    # holder in the in-process registry. ANY exit path that doesn't have
    # a real decision must finalise both — including CancelledError
    # (FastAPI client disconnect). We can't await cleanup directly in
    # the finally of a cancelling task because that re-raises
    # CancelledError before the awaited body runs; instead we spawn
    # cleanup as a free-running task on the loop.
    cleanup_done = False
    try:
        event = await decisions.register(request_id)
        # Emit on the bus so the dashboard's PendingApprovalsBanner gets
        # a push event regardless of whether the ntfy notification is up.
        await bus.publish(
            BusEvent(
                kind="permission_request",
                session_id=session_id,
                data={
                    "id": request_id,
                    "session_id": session_id,
                    "tool_use_id": tool_use_id,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "requested_at": requested_at,
                },
            )
        )

        # Fire ntfy push best-effort. ntfy module already drops on no-topic.
        try:
            from csm.ntfy import push_permission_request

            await push_permission_request(
                conn,
                request_id=request_id,
                session_id=session_id,
                tool_name=tool_name,
            )
        except Exception:
            log.exception("permission ntfy push failed (continuing)")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_ms / 1000.0)
        except TimeoutError:
            # Inline cleanup — we're not being cancelled, just
            # naturally timing out. Awaiting here is safe.
            await _finalize_timeout(conn, request_id)
            cleanup_done = True
            return DecisionResult(decision=None, reason=None)

        decision, reason = await decisions.collect(request_id)
        cleanup_done = True
        # If the holder was popped with no decision (shouldn't happen
        # given register() pre-sets the Event only when a deferred
        # decision is present), fall back to a timeout-style cleanup.
        if decision is None:
            cleanup_done = False
            await _finalize_timeout(conn, request_id)
            cleanup_done = True
            return DecisionResult(decision=None, reason=None)
        return DecisionResult(decision=decision, reason=reason)
    finally:
        if not cleanup_done:
            try:
                loop = asyncio.get_running_loop()
                # Keep a strong reference to the cleanup task so the
                # loop's weakref-keyed task set doesn't GC it before
                # it can flip the DB row to timed_out.
                _register_cleanup_task(loop.create_task(_finalize_timeout(conn, request_id)))
            except RuntimeError:
                # No loop — synchronous path; row will be swept by
                # cleanup_stale_pending on next startup.
                pass


async def _finalize_timeout(conn: Any, request_id: int) -> None:
    """Cleanup helper: mark the row timed_out and drop the holder.

    Safe to call multiple times — the UPDATE is bounded by
    ``status = 'pending'`` so an already-decided row is untouched.
    Spawned as a free-running task by callers so cancellation of the
    parent task can't abort the DB write.
    """
    decided_at = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _timeout_update() -> None:
        conn.execute(
            "UPDATE permission_requests "
            "SET status = 'timed_out', decided_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (decided_at, request_id),
        )

    try:
        await asyncio.to_thread(_timeout_update)
    except Exception:
        log.exception("permissions: failed to mark row %d timed_out", request_id)
    await decisions.cancel(request_id)


async def record_decision(
    conn: Any,
    *,
    request_id: int,
    decision: str,
    reason: str | None,
) -> bool:
    """Persist the decision + signal the awaiting receiver. Returns True
    if the row was pending (and we successfully transitioned it), False
    if the row was already in a terminal state."""
    if decision not in ("allow", "deny", "ask"):
        raise ValueError(f"unknown decision: {decision!r}")

    decided_at = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _update() -> int:
        cursor = conn.execute(
            "UPDATE permission_requests "
            "SET status = ?, decision_reason = ?, decided_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (decision, reason, decided_at, request_id),
        )
        return int(cursor.rowcount or 0)

    rowcount = await asyncio.to_thread(_update)
    if rowcount == 0:
        return False
    # deliver() now always returns True — it either signals a live
    # waiter or stashes the decision in _deferred for whoever registers
    # next (closes the INSERT-then-register race in request_decision).
    await decisions.deliver(request_id, decision, reason)
    return True


# ──────────────────────────── startup hygiene ────────────────────────────


def cleanup_stale_pending(conn: Any, *, max_age_seconds: int = 3600) -> int:
    """On collector startup, mark any ``pending`` rows older than
    ``max_age_seconds`` as ``timed_out``. They couldn't have an awaiting
    receiver after a process restart — the in-memory PendingDecisions
    registry is empty. Returns the row-count touched.
    """
    cutoff = (datetime.now(tz=UTC) - timedelta(seconds=max_age_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor = conn.execute(
        "UPDATE permission_requests "
        "SET status = 'timed_out', decided_at = ? "
        "WHERE status = 'pending' AND requested_at <= ?",
        (now, cutoff),
    )
    rowcount = int(cursor.rowcount or 0)
    if rowcount:
        log.info(
            "permissions: marked %d stale pending requests as timed_out on startup",
            rowcount,
        )
    # Also: any pending row whose process-lifetime registration is gone
    # (we just started up — all of them) needs to be cleaned up if not
    # already. The max_age_seconds catches anything OLDER; recent ones
    # we leave as pending because they may have been written by us
    # before a partial-restart and the dashboard could still surface them.
    _ = contextlib  # quiet unused-import
    return rowcount
