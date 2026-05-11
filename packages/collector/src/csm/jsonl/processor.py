"""Read new bytes from a JSONL file at its tracked offset, persist messages.

This is the synchronous core. The watchdog observer (``watcher.py``)
calls into here on every FS event; the initial-scan path also calls
here. Tests bypass watchdog and call ``process_file`` directly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from csm.bus import BusEvent, bus
from csm.hooks.state_machine import utcnow_iso
from csm.jsonl.offsets import current_inode, get_offset, upsert_offset
from csm.jsonl.parser import ParsedMessage, ParseError, parse_line

log = logging.getLogger(__name__)


def session_id_from_path(path: Path) -> str:
    """Filename minus ``.jsonl`` is the session_id."""
    return path.stem


def process_file(conn: Any, path: Path) -> int:
    """Read new lines from ``path`` past its tracked offset, persist them.

    Returns the number of new transcript messages persisted. Idempotent
    — calling twice with no new content is a no-op.

    Resilience:
    - Trailing partial line (no newline yet) is buffered until the next
      call.
    - Garbage lines are logged and skipped; ingestion continues.
    - File rotation is detected via inode change → offset resets to 0.
    - Missing file → offset cleared via ``last_seen`` only (no error).
    """
    if not path.exists():
        log.warning("jsonl: %s vanished before processing", path)
        return 0

    inode_now = current_inode(path)
    prior = get_offset(conn, path)
    start_offset = 0
    if prior is not None and prior.last_inode == inode_now:
        start_offset = prior.byte_offset

    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return 0

    if size < start_offset:
        # File was truncated/replaced without inode change. Re-read everything.
        log.info("jsonl: %s truncated; resetting offset", path)
        start_offset = 0

    if size == start_offset:
        return 0

    with path.open("rb") as fh:
        fh.seek(start_offset)
        chunk = fh.read()

    # Find the last newline in RAW BYTES — never re-encode decoded text for
    # offset arithmetic. The UTF-8 decoder's ``errors="replace"`` substitutes
    # U+FFFD (3 bytes encoded) for any invalid sequence, so
    # ``len(text.encode("utf-8"))`` drifts relative to the original file
    # whenever a malformed byte appears. Working on bytes keeps the offset
    # exactly aligned even through corrupted regions.
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        # Whole chunk is a partial line — defer until a newline arrives.
        return 0
    raw_complete = chunk[: last_nl + 1]
    new_offset = start_offset + len(raw_complete)
    text = raw_complete.decode("utf-8", errors="replace")
    sid = session_id_from_path(path)
    persisted = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            parsed = parse_line(line)
        except ParseError as exc:
            log.warning("jsonl: %s skipping garbage line: %s", path, exc)
            continue
        _persist(conn, sid, parsed)
        persisted += 1

    upsert_offset(
        conn,
        path,
        byte_offset=new_offset,
        last_inode=inode_now,
        last_seen=utcnow_iso(),
    )
    if persisted:
        # If this was the FIRST signal we had of this session (no SessionStart
        # hook fired yet), the sessions row has worktree_root="". Derive
        # worktree from the JSONL transcript path so the tree builder can
        # find a parent. Otherwise the session is permanently orphaned at
        # the project-root level.
        _backfill_worktree_and_resolve_parent(conn, path, sid)
        _emit(sid, persisted)
    return persisted


def _derive_worktree_from_jsonl_path(jsonl_path: Path) -> str:
    """Reverse Claude Code's ``cwd → encoded-dirname`` mapping to recover
    the worktree root.

    Path shape: ``~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl``,
    where ``<encoded-cwd>`` is the absolute cwd with ``/`` → ``-``. We
    decode by prefixing ``/`` and replacing ``-`` with ``/``. This is
    ambiguous if the original path contained a literal ``-`` (e.g.
    ``/Users/hank-h/foo``); ``resolve_worktree`` walks up to the nearest
    ``.git`` from the decoded candidate, so a real repo usually surfaces
    even when the decode isn't pixel-perfect.

    Returns ``""`` if the path doesn't match the Claude Code shape.
    """
    from csm.hooks.worktree import resolve_worktree

    encoded = jsonl_path.parent.name
    if not encoded.startswith("-"):
        return ""
    decoded = encoded.replace("-", "/")
    return resolve_worktree(decoded)


def _backfill_worktree_and_resolve_parent(
    conn: Any, jsonl_path: Path, session_id: str
) -> None:
    row = conn.execute(
        "SELECT worktree_root FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    if row is None or row[0]:
        # Either no row (race) or hooks already populated worktree_root.
        return
    derived = _derive_worktree_from_jsonl_path(jsonl_path)
    if not derived:
        return
    from csm.hooks.worktree import project_label

    conn.execute(
        "UPDATE sessions SET worktree_root = ?, project_label = ? WHERE session_id = ?",
        (derived, project_label(derived), session_id),
    )
    from csm.tree import resolve_parent

    resolve_parent(conn, session_id)


def _persist(conn: Any, session_id: str, parsed: ParsedMessage) -> None:
    """Insert one row into transcript_messages (and optionally upsert session)."""
    # Ensure a sessions row exists — if hooks haven't run yet, the
    # JSONL may be the first signal we have for this session.
    conn.execute(
        """
        INSERT OR IGNORE INTO sessions (
            session_id, worktree_root, cwd, last_event_at, started_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, "", "", parsed.timestamp, parsed.timestamp),
    )
    conn.execute(
        """
        INSERT INTO transcript_messages (
            session_id, role, timestamp, content_json, model,
            input_tokens, output_tokens,
            cache_creation_input_tokens, cache_read_input_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            parsed.role,
            parsed.timestamp,
            parsed.content_json,
            parsed.model,
            parsed.input_tokens,
            parsed.output_tokens,
            parsed.cache_creation_input_tokens,
            parsed.cache_read_input_tokens,
        ),
    )


def _emit(session_id: str, count: int) -> None:
    """Schedule a bus publish if an asyncio loop is running.

    The watcher thread isn't an asyncio context — we use
    ``run_coroutine_threadsafe`` to bridge. In tests there's typically
    no running loop, so we degrade silently.
    """
    import asyncio

    event = BusEvent(
        kind="transcript_message",
        session_id=session_id,
        data={"persisted": count},
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.run_coroutine_threadsafe(bus.publish(event), loop)
