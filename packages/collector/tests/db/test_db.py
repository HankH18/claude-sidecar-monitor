"""DB layer tests — migration runner + encrypted roundtrip."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
import sqlcipher3

from csm.db import connect


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "store.db"


def test_fresh_db_creates_schema(tmp_db: Path) -> None:
    conn = connect(db_path=tmp_db)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    table_names = {row[0] for row in rows}
    assert {"sessions", "events", "transcript_messages", "settings", "_offsets", "_migrations"} <= (
        table_names
    )


def test_seed_settings_present(tmp_db: Path) -> None:
    conn = connect(db_path=tmp_db)
    try:
        seeds = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    finally:
        conn.close()
    assert seeds == {
        "hang_yellow_ms": "60000",
        "hang_red_ms": "180000",
        "ntfy_topic": "",
    }
    # plan_seat_type was explicitly removed from the seed (T4 amendment).
    assert "plan_seat_type" not in seeds


def test_migration_idempotent(tmp_db: Path) -> None:
    """Re-opening the DB must not re-run migrations."""
    c1 = connect(db_path=tmp_db)
    try:
        applied_v1 = c1.execute("SELECT count(*) FROM _migrations").fetchone()[0]
    finally:
        c1.close()

    c2 = connect(db_path=tmp_db)
    try:
        applied_v2 = c2.execute("SELECT count(*) FROM _migrations").fetchone()[0]
        # No duplicate inserts on the second open.
        assert applied_v2 == applied_v1
    finally:
        c2.close()


def test_token_columns_round_trip(tmp_db: Path) -> None:
    """T4 amendment: sessions has 4 token columns."""
    conn = connect(db_path=tmp_db)
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, worktree_root, cwd, last_event_at, started_at,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "abc-123",
                "/tmp/proj",
                "/tmp/proj",
                "2026-05-10T00:00:00Z",
                "2026-05-10T00:00:00Z",
                100,
                200,
                300,
                400,
            ),
        )
        row = conn.execute(
            "SELECT input_tokens, output_tokens, cache_read_tokens, cache_write_tokens "
            "FROM sessions WHERE session_id=?",
            ("abc-123",),
        ).fetchone()
    finally:
        conn.close()
    assert row == (100, 200, 300, 400)


def test_encrypted_round_trip(tmp_db: Path) -> None:
    """Open with key → write → close → reopen with same key → read."""
    key = secrets.token_bytes(32)

    c1 = connect(key=key, db_path=tmp_db)
    try:
        c1.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ("custom_setting", "encrypted-value"),
        )
    finally:
        c1.close()

    c2 = connect(key=key, db_path=tmp_db)
    try:
        value = c2.execute(
            "SELECT value FROM settings WHERE key=?", ("custom_setting",)
        ).fetchone()[0]
    finally:
        c2.close()

    assert value == "encrypted-value"


def test_encrypted_db_rejects_wrong_key(tmp_db: Path) -> None:
    key_a = secrets.token_bytes(32)
    key_b = secrets.token_bytes(32)
    assert key_a != key_b

    c = connect(key=key_a, db_path=tmp_db)
    c.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("foo", "bar"))
    c.close()

    with pytest.raises(sqlcipher3.DatabaseError):
        connect(key=key_b, db_path=tmp_db)


def test_encrypted_bytes_look_random(tmp_db: Path) -> None:
    """Acceptance criterion #11: ``xxd store.db | head`` shows random bytes."""
    key = secrets.token_bytes(32)
    conn = connect(key=key, db_path=tmp_db)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ("k", "the-quick-brown-fox-jumps-over"),
        )
    finally:
        conn.close()

    raw = tmp_db.read_bytes()
    # SQLCipher v4 page format: NO "SQLite format 3" magic in the header.
    assert b"SQLite format 3" not in raw[:64]
    # Cleartext from our insert must not appear in the encrypted file.
    assert b"the-quick-brown-fox-jumps-over" not in raw


def test_unkeyed_db_is_plain_sqlite(tmp_db: Path) -> None:
    conn = connect(db_path=tmp_db)
    try:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("look", "plaintext"))
    finally:
        conn.close()
    raw = tmp_db.read_bytes()
    assert raw.startswith(b"SQLite format 3\x00")
    assert b"plaintext" in raw
