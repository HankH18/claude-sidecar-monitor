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

    text = chunk.decode("utf-8", errors="replace")
    if not text.endswith("\n"):
        # Keep the partial line for next round — only advance offset
        # past the last completed newline.
        last_nl = text.rfind("\n")
        if last_nl == -1:
            return 0
        text = text[: last_nl + 1]

    new_offset = start_offset + len(text.encode("utf-8"))
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
        _emit(sid, persisted)
    return persisted


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
