"""Session activity digest (V2.B).

Derive a single human-readable line summarising what a session is doing
right now — for the dashboard's overview row + the phone-shaped session
card. No LLM calls; pure rules over the structured data we already
persist (``events``, ``transcript_messages``, ``permission_requests``).

Heuristics (first match wins):

1. Any pending ``permission_requests`` row
   →  "Awaiting approval for {tool_name}"
2. Most recent ``PreToolUse`` event without a matching ``PostToolUse``
   in the last 30s
   →  "Running {tool_name}" (lightly specialised per-tool:
      Bash → command snippet, Read/Edit/Write → basename,
      Agent → "Delegating to subagent")
3. Last ``assistant`` message within the last 5 minutes
   →  first sentence (or 80 chars) of its text content
4. Last ``user`` prompt within the last 5 minutes, with no assistant
   reply since
   →  "Working on: {prompt snippet}"
5. Otherwise → (None, None)

Public surface:

- :func:`derive_session_digest` — pure synchronous function returning
  ``(summary, generated_at_iso) | (None, None)``.
- :func:`apply_digest_update` — recompute, compare against the current
  ``sessions.activity_summary``, and (if changed) persist + return the
  new value. Designed to be called from inside the state-machine
  transaction or from a read-path lazily.
"""

from __future__ import annotations

import json
import os.path
import re
from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = [
    "ACTIVE_TOOL_WINDOW_S",
    "RECENT_TEXT_WINDOW_S",
    "SUMMARY_MAX_LEN",
    "apply_digest_update",
    "compute_session_digest",
    "derive_session_digest",
]

# Window during which a PreToolUse without a matching PostToolUse counts
# as "active". Most tools finish under a few seconds; a 30s ceiling
# catches genuine in-flight work without over-claiming for tools that
# legitimately stalled (those become hang/yellow in the state column).
ACTIVE_TOOL_WINDOW_S = 30

# How recent the last message has to be to surface in the digest.
RECENT_TEXT_WINDOW_S = 5 * 60

# Truncation budget for summaries — matches TITLE_MAX_LEN for visual
# consistency with the session-card identity row.
SUMMARY_MAX_LEN = 80


# ────────────────────────── public API ──────────────────────────


def derive_session_digest(
    conn: Any,
    session_id: str,
    *,
    now: datetime | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(summary, generated_at_iso)`` or ``(None, None)``.

    Pure synchronous read — never writes to the DB. Caller is
    responsible for transactionality.

    ``now`` is injectable for tests; production passes None and we
    use the current UTC clock.
    """
    current = now or datetime.now(tz=UTC)
    generated_at = current.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Pending approval — highest priority.
    approval = _pending_approval(conn, session_id)
    if approval is not None:
        return f"Awaiting approval for {approval}", generated_at

    # 2. Active tool call.
    active = _active_tool(conn, session_id, current)
    if active is not None:
        return active, generated_at

    # 3 / 4. Recent assistant text / user prompt.
    recent = _recent_message_digest(conn, session_id, current)
    if recent is not None:
        return recent, generated_at

    return None, None


def compute_session_digest(
    conn: Any,
    session_id: str,
    *,
    now: datetime | None = None,
) -> tuple[str | None, str | None]:
    """Alias for :func:`derive_session_digest`.

    Two names because the caller-side terminology varies:
    ingest-side ``derive_``, read-side ``compute_``. Keeping both
    keeps the wiring code readable.
    """
    return derive_session_digest(conn, session_id, now=now)


def apply_digest_update(
    conn: Any,
    session_id: str,
    *,
    now: datetime | None = None,
) -> tuple[str | None, str | None, bool]:
    """Recompute the digest and, if it differs from the persisted
    ``sessions.activity_summary``, write the new value + timestamp.

    Returns ``(summary, generated_at, changed)``. Callers use
    ``changed`` to decide whether to publish a ``session_digest_update``
    BusEvent.

    Wrap in the same DB connection the caller is using. This function
    does NOT manage transactions — the state-machine writer that calls
    it is already inside BEGIN IMMEDIATE/COMMIT; the read-path callers
    invoke it outside any explicit transaction (autocommit mode).
    """
    summary, generated_at = derive_session_digest(conn, session_id, now=now)

    prior = conn.execute(
        "SELECT activity_summary FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    prior_summary = prior[0] if prior is not None else None

    if summary == prior_summary:
        # No-op — don't churn activity_updated_at on every read, and
        # don't fire an SSE event on stable state.
        return summary, generated_at, False

    conn.execute(
        "UPDATE sessions SET activity_summary = ?, activity_updated_at = ? "
        "WHERE session_id = ?",
        (summary, generated_at, session_id),
    )
    return summary, generated_at, True


# ────────────────────────── heuristic 1: approvals ──────────────────────────


def _pending_approval(conn: Any, session_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT tool_name FROM permission_requests
        WHERE session_id = ? AND status = 'pending'
        ORDER BY requested_at DESC, id DESC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]) if row[0] else "tool"


# ────────────────────────── heuristic 2: active tool ──────────────────────────


def _active_tool(conn: Any, session_id: str, now: datetime) -> str | None:
    """Look for a PreToolUse without a corresponding PostToolUse (matched
    on tool_use_id when available, fallback to "no Post since the Pre")."""
    cutoff = (now - timedelta(seconds=ACTIVE_TOOL_WINDOW_S)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    row = conn.execute(
        """
        SELECT event_id, tool_name, tool_use_id, payload_json, received_at
        FROM events
        WHERE session_id = ?
          AND event_name = 'PreToolUse'
          AND received_at >= ?
        ORDER BY event_id DESC
        LIMIT 1
        """,
        (session_id, cutoff),
    ).fetchone()
    if row is None:
        return None

    pre_event_id, tool_name, tool_use_id, payload_json, _ = row
    if not tool_name:
        return None

    # Confirm no matching PostToolUse closed it. Match on tool_use_id
    # if both Pre and Post carried one; otherwise fall back to
    # "any PostToolUse with the same tool_name AFTER this Pre".
    if tool_use_id:
        post = conn.execute(
            """
            SELECT 1 FROM events
            WHERE session_id = ?
              AND event_name = 'PostToolUse'
              AND tool_use_id = ?
            LIMIT 1
            """,
            (session_id, tool_use_id),
        ).fetchone()
    else:
        post = conn.execute(
            """
            SELECT 1 FROM events
            WHERE session_id = ?
              AND event_name = 'PostToolUse'
              AND tool_name = ?
              AND event_id > ?
            LIMIT 1
            """,
            (session_id, tool_name, pre_event_id),
        ).fetchone()
    if post is not None:
        return None

    return _describe_active_tool(str(tool_name), payload_json)


def _describe_active_tool(tool_name: str, payload_json: str | None) -> str:
    """Tool-specific specialisation. Best-effort; falls back to
    "Running {tool_name}" on any parse failure or missing field."""
    payload = _safe_json_loads(payload_json) if payload_json else None
    tool_input = (
        payload.get("tool_input")
        if isinstance(payload, dict) and isinstance(payload.get("tool_input"), dict)
        else None
    )

    if tool_name == "Agent":
        return "Delegating to subagent"

    if tool_name == "Bash" and tool_input:
        cmd = tool_input.get("command")
        if isinstance(cmd, str) and cmd.strip():
            return f"Running Bash: {_truncate(cmd.strip(), 40)}"
        return "Running Bash"

    if tool_name == "Read" and tool_input:
        base = _basename_of(tool_input.get("file_path"))
        if base:
            return f"Reading {base}"
        return "Reading"

    if tool_name in ("Edit", "Write", "MultiEdit") and tool_input:
        base = _basename_of(tool_input.get("file_path"))
        if base:
            verb = "Editing" if tool_name in ("Edit", "MultiEdit") else "Writing"
            return f"{verb} {base}"

    return f"Running {tool_name}"


def _basename_of(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    base = os.path.basename(value.rstrip("/"))
    return base or None


# ────────────────────────── heuristic 3 / 4: recent text ──────────────────────────


# First-sentence regex: ends at the first ., !, or ? followed by whitespace
# or end-of-string. We deliberately don't try to handle abbreviations
# ("e.g.", "etc.") — close enough for a one-line digest.
_SENTENCE_END_RE = re.compile(r"^([^.!?\n]+[.!?])(?:\s|$)")


def _recent_message_digest(
    conn: Any, session_id: str, now: datetime
) -> str | None:
    cutoff = (now - timedelta(seconds=RECENT_TEXT_WINDOW_S)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # Pull the most recent assistant + user messages in the window in
    # a single scan, ordered newest-first.
    rows = conn.execute(
        """
        SELECT role, timestamp, content_json
        FROM transcript_messages
        WHERE session_id = ?
          AND timestamp >= ?
          AND role IN ('assistant', 'user')
        ORDER BY message_id DESC
        LIMIT 20
        """,
        (session_id, cutoff),
    ).fetchall()
    if not rows:
        return None

    # Find the newest assistant message (heuristic 3) and the newest
    # user prompt (heuristic 4). Track positional ordering so we can
    # detect "user prompt with no assistant reply since".
    newest_assistant: tuple[str, str] | None = None  # (timestamp, content_json)
    newest_user: tuple[str, str] | None = None
    for role, timestamp, content_json in rows:
        if role == "assistant" and newest_assistant is None:
            newest_assistant = (timestamp, content_json)
        elif role == "user" and newest_user is None:
            newest_user = (timestamp, content_json)
        if newest_assistant and newest_user:
            break

    # Heuristic 3: assistant text wins when it's the newest signal.
    if newest_assistant is not None:
        # If the latest message is assistant, OR no user-after-assistant
        # exists, surface the assistant text.
        a_ts, a_content = newest_assistant
        if newest_user is None or newest_user[0] <= a_ts:
            text = _extract_assistant_text(a_content)
            if text:
                return _first_sentence(text)

    # Heuristic 4: user prompt with no assistant reply since.
    if newest_user is not None:
        u_ts, u_content = newest_user
        if newest_assistant is None or newest_assistant[0] < u_ts:
            prompt = _extract_user_text(u_content)
            if prompt:
                return f"Working on: {_truncate(prompt, SUMMARY_MAX_LEN - len('Working on: '))}"

    return None


def _extract_assistant_text(content_json: str) -> str | None:
    """Pull the first text block out of an assistant transcript line."""
    obj = _safe_json_loads(content_json)
    if not isinstance(obj, dict):
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    # ``content`` can be a string (legacy) or a list of blocks (current).
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    return None


def _extract_user_text(content_json: str) -> str | None:
    """Pull the user prompt text. Skip tool_result / system content."""
    obj = _safe_json_loads(content_json)
    if not isinstance(obj, dict):
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
        # Skip pure tool-result follow-ups and harness wrappers.
        if not text or text.startswith(("[Tool result", "[System", "[Continuing")):
            return None
        return text
    if isinstance(content, list):
        # Look for the first plain text block; ignore tool_result blocks.
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                block_text = block.get("text")
                if isinstance(block_text, str) and block_text.strip():
                    return block_text.strip()
    return None


def _first_sentence(text: str) -> str:
    """Take the first sentence (`.!?`-terminated) or the first
    ``SUMMARY_MAX_LEN`` chars, whichever is shorter."""
    # Collapse internal whitespace so multi-line answers don't get a
    # newline in the middle of the digest.
    flat = " ".join(text.split())
    match = _SENTENCE_END_RE.match(flat)
    if match:
        sentence = match.group(1).strip()
        if len(sentence) <= SUMMARY_MAX_LEN:
            return sentence
    return _truncate(flat, SUMMARY_MAX_LEN)


# ────────────────────────── shared utilities ──────────────────────────


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 1:
        return text[:max_len]
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1]
    last_space = cut.rfind(" ")
    if last_space > max_len // 2:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def _safe_json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
