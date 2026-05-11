"""Idempotent migration runner.

Applies every ``NNN_*.sql`` file under ``migrations/`` whose version
number isn't already in the ``_migrations`` tracking table. Versions
are integers parsed from the filename prefix (``001`` → 1).

Intentionally minimal — no down-migrations, no DSL, no transaction
wrapping beyond what ``executescript`` provides. Schema changes ship
as new files; we never edit a migration that has shipped.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

_MIGRATION_FILE = re.compile(r"^(\d{3,})_.+\.sql$")

# Stripping line + block comments + statement splitting on top-level `;`.
# Our migration files don't contain semicolons inside string literals (DDL
# only), so a simple split is safe. We strip `-- ...` line comments and
# `/* ... */` block comments before splitting so a `;` inside a comment
# can't fool us.
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _split_sql_statements(sql: str) -> list[str]:
    """Split a migration script into individual statements suitable for
    ``conn.execute()`` inside an explicit transaction. Strips comments
    first so a `;` inside a comment doesn't become a statement boundary.
    """
    stripped = _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", sql))
    return [stmt.strip() for stmt in stripped.split(";") if stmt.strip()]


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
        # We split-and-execute statements inside an explicit BEGIN IMMEDIATE
        # / COMMIT rather than using ``conn.executescript()``. In our
        # autocommit-mode connection (isolation_level=None), executescript
        # commits each statement individually — wrapping it in BEGIN/COMMIT
        # doesn't survive, and a partial-execute crash leaves the DB in
        # an inconsistent state for any future non-idempotent migration
        # (CREATE TABLE IF NOT EXISTS is fine today; ALTER TABLE + data
        # backfill in 002+ won't be). The split approach gives us real
        # atomicity: either every statement in the migration applies AND
        # the _migrations row is recorded, or nothing is.
        statements = _split_sql_statements(sql)
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in statements:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
            conn.execute("COMMIT")
        except Exception:
            with contextlib.suppress(Exception):
                conn.execute("ROLLBACK")
            raise
        count += 1
    return count
