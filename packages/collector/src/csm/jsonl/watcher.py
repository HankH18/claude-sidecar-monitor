"""``watchdog`` Observer that tails Claude Code's JSONL transcripts.

Lifecycle:

- ``start()`` scans the projects directory for existing JSONL files and
  catches up each one to its tail. Then registers FSEvents handlers
  and starts the observer thread.
- The observer fires synchronously into ``_on_modified`` /
  ``_on_created`` which call ``process_file``.
- ``stop()`` joins the observer thread.

We intentionally DON'T use watchdog's polling fallback — FSEvents on
macOS is sufficient, and polling would add CPU overhead.
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import RLock
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from csm.jsonl.processor import process_file

log = logging.getLogger(__name__)


class _JsonlHandler(FileSystemEventHandler):
    """Bridge watchdog events → ``process_file`` calls."""

    def __init__(self, watcher: JsonlWatcher) -> None:
        self._watcher = watcher

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if not str(event.src_path).endswith(".jsonl"):
            return
        self._watcher.process(Path(str(event.src_path)))

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if not str(event.src_path).endswith(".jsonl"):
            return
        self._watcher.process(Path(str(event.src_path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # File rotation: process the new path from scratch.
        dest = getattr(event, "dest_path", None)
        if isinstance(dest, str) and dest.endswith(".jsonl"):
            self._watcher.process(Path(dest))


class JsonlWatcher:
    """FSEvents-driven JSONL ingestion.

    Holds a reference to the DB connection and serialises all DB writes
    through ``self._lock`` so concurrent FSEvents callbacks don't
    interleave inside SQLite.
    """

    def __init__(self, conn: Any, projects_dir: Path) -> None:
        self.conn = conn
        self.projects_dir = projects_dir
        # ``Observer`` from watchdog is exported as a callable that
        # returns a platform-specific subclass — we type-hint with
        # ``Any`` to avoid clashing with watchdog's lazy class shim.
        self._observer: Any = None
        self._lock = RLock()

    def start(self) -> None:
        """Catch up existing files, then begin watching."""
        if not self.projects_dir.exists():
            log.info("jsonl: projects dir %s missing; nothing to watch", self.projects_dir)
            return

        # Initial scan — catch up every existing JSONL.
        for jsonl in self.projects_dir.rglob("*.jsonl"):
            self.process(jsonl)

        observer = Observer()
        observer.schedule(_JsonlHandler(self), str(self.projects_dir), recursive=True)
        observer.start()
        self._observer = observer
        log.info("jsonl: watching %s", self.projects_dir)

    def stop(self, *, timeout: float = 2.0) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=timeout)
        self._observer = None

    def process(self, path: Path) -> int:
        """Thread-safe wrapper around :func:`process_file`."""
        with self._lock:
            try:
                return process_file(self.conn, path)
            except Exception:
                log.exception("jsonl: process_file failed for %s", path)
                return 0
