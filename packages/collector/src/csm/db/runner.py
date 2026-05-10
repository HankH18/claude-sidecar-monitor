"""Idempotent migration runner.

Applies every ``NNN_*.sql`` file under ``migrations/`` whose version
number isn't already in the ``_migrations`` tracking table. Versions
are integers parsed from the filename prefix (``001`` → 1).

Intentionally minimal — no down-migrations, no DSL, no transaction
wrapping beyond what ``executescript`` provides. Schema changes ship
as new files; we never edit a migration that has shipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_MIGRATION_FILE = re.compile(r"^(\d{3,})_.+\.sql$")


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def discover() -> list[tuple[int, str, Path]]:
    """Return ``(version, name, path)`` tuples sorted by version."""
    out: list[tuple[int, str, Path]] = []
    for path in sorted(_migrations_dir().glob("*.sql")):
        m = _MIGRATION_FILE.match(path.name)
        if not m:
            continue
        version = int(m.group(1))
        out.append((version, path.stem, path))
    return sorted(out, key=lambda t: t[0])


def apply_migrations(conn: Any) -> int:
    """Apply all pending migrations. Returns the number applied."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM _migrations").fetchall()}

    count = 0
    for version, name, path in discover():
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        # ``executescript`` in autocommit mode (our default) commits each
        # statement as it goes, so we don't wrap in BEGIN/COMMIT — that
        # would be auto-committed away. Migrations themselves are written
        # with ``IF NOT EXISTS`` / ``OR IGNORE`` so a partial failure
        # leaves the schema re-runnable on the next start-up.
        conn.executescript(sql)
        conn.execute("INSERT INTO _migrations (version, name) VALUES (?, ?)", (version, name))
        count += 1
    return count
