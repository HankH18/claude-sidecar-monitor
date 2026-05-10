"""I/O helpers for the ``_offsets`` table (per-file resume state)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Offset:
    file_path: str
    byte_offset: int
    last_inode: int | None
    last_seen: str


def get_offset(conn: Any, path: Path) -> Offset | None:
    row = conn.execute(
        "SELECT file_path, byte_offset, last_inode, last_seen FROM _offsets WHERE file_path=?",
        (str(path),),
    ).fetchone()
    if row is None:
        return None
    return Offset(file_path=row[0], byte_offset=row[1], last_inode=row[2], last_seen=row[3])


def upsert_offset(
    conn: Any, path: Path, byte_offset: int, last_inode: int | None, last_seen: str
) -> None:
    conn.execute(
        """
        INSERT INTO _offsets (file_path, byte_offset, last_inode, last_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(file_path) DO UPDATE SET
            byte_offset = excluded.byte_offset,
            last_inode  = excluded.last_inode,
            last_seen   = excluded.last_seen
        """,
        (str(path), byte_offset, last_inode, last_seen),
    )


def current_inode(path: Path) -> int | None:
    """Return the file's inode, or ``None`` if it doesn't exist."""
    try:
        return os.stat(path).st_ino
    except FileNotFoundError:
        return None
