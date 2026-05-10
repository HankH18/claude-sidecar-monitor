"""Claude Code JSONL transcript watcher (T7).

The receiver path (T6) gives us low-latency state changes but doesn't
carry per-message token usage or full prompt/response content. This
module fills both gaps by tailing the JSONL files Claude Code writes
to ``~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl``.

Public surface:

- ``JsonlWatcher`` — owns a watchdog Observer; ``start()`` and
  ``stop()`` lifecycle methods.
- ``process_file(conn, path)`` — read new bytes from the file at its
  last known offset, parse each completed line, persist to
  ``transcript_messages``, update ``_offsets``, emit on the bus.
- ``parse_line(raw)`` — turn a JSONL string into the row shape used
  by ``transcript_messages``.
"""

from __future__ import annotations

from csm.jsonl.parser import ParsedMessage, parse_line
from csm.jsonl.processor import process_file
from csm.jsonl.watcher import JsonlWatcher

__all__ = ["JsonlWatcher", "ParsedMessage", "parse_line", "process_file"]
