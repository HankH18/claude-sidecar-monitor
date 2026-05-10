"""SQLite/SQLCipher connection + migration entry point.

Public surface:

- ``connect(key=None, db_path=None)`` returns a fresh ``sqlcipher3``
  connection with WAL mode and FK constraints enabled, applies any
  pending migrations, and returns it ready for use.
- ``hex_key(raw)`` formats a raw 32-byte key for SQLCipher's PRAGMA.

The ``key`` parameter accepts either:
- ``None`` — open as plain SQLite (used by tests that don't exercise
  encryption).
- ``bytes`` — a raw 32-byte key (typically derived via Argon2id by
  ``csm.crypto``); passed to ``PRAGMA key = "x'<hex>'"``.

T29's ``csm.crypto`` is the canonical caller in production. Test code
exercises both modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import sqlcipher3

from csm.config import Paths
from csm.db.runner import apply_migrations

__all__ = [
    "Connection",
    "DatabaseError",
    "connect",
    "hex_key",
]


# sqlcipher3 lacks type stubs — alias for clarity in callers.
Connection = Any
DatabaseError = sqlcipher3.DatabaseError


def hex_key(raw: bytes) -> str:
    """Format a raw 32-byte key for use in ``PRAGMA key``."""
    if len(raw) != 32:
        raise ValueError(f"expected 32-byte key, got {len(raw)} bytes")
    return raw.hex()


def connect(
    key: bytes | None = None,
    db_path: Path | None = None,
    *,
    apply_migrations_on_open: bool = True,
) -> Connection:
    """Open (and optionally migrate) the collector database.

    The returned connection is in **autocommit** mode (``isolation_level=None``)
    so callers manage transactions explicitly with ``BEGIN``/``COMMIT``. This
    avoids surprises with the implicit-transaction wrapping that sqlite3's
    default isolation_level imposes.
    """
    path = db_path if db_path is not None else Paths.from_env().db
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    # ``check_same_thread=False`` so the FastAPI ``asyncio.to_thread`` worker
    # pool can use the connection. With WAL mode this is safe for many
    # readers and a few writers — SQLite serialises writes itself.
    conn = cast(
        Connection,
        sqlcipher3.connect(str(path), isolation_level=None, check_same_thread=False),
    )
    try:
        if key is not None:
            # Use raw-key syntax (skip SQLCipher's own KDF — we did Argon2id).
            conn.execute(f"PRAGMA key = \"x'{hex_key(key)}'\"")
            # Force a read so a wrong key fails fast with DatabaseError.
            # SQLCipher returns garbage on the SELECT until something is read.
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        if apply_migrations_on_open:
            apply_migrations(conn)
    except Exception:
        conn.close()
        raise

    return conn
