"""Tests for ``csm purge``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from csm import crypto
from csm.cli import app as cli_app
from csm.cli.purge import parse_duration
from csm.db import connect


@pytest.fixture
def keychain_stub(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    store: dict[tuple[str, str], str] = {}

    def _set(service: str, account: str, password: str) -> None:
        store[(service, account)] = password

    def _get(service: str, account: str) -> str | None:
        return store.get((service, account))

    def _delete(service: str, account: str) -> None:
        if (service, account) not in store:
            import keyring.errors

            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, account)]

    monkeypatch.setattr(crypto.keyring, "set_password", _set)
    monkeypatch.setattr(crypto.keyring, "get_password", _get)
    monkeypatch.setattr(crypto.keyring, "delete_password", _delete)
    return store


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CSM_APP_SUPPORT", str(tmp_path / "support"))
    monkeypatch.setenv("CSM_DB_PATH", str(tmp_path / "support" / "store.db"))
    monkeypatch.setenv("CSM_SALT_PATH", str(tmp_path / "support" / "store.salt"))
    monkeypatch.setenv("CSM_LOG_DIR", str(tmp_path / "logs"))
    return tmp_path


# ────────────────────── duration parser ──────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("30s", timedelta(seconds=30)),
        ("5m", timedelta(minutes=5)),
        ("24h", timedelta(hours=24)),
        ("30d", timedelta(days=30)),
        ("2w", timedelta(weeks=2)),
    ],
)
def test_parse_duration_valid(raw: str, expected: timedelta) -> None:
    assert parse_duration(raw) == expected


@pytest.mark.parametrize("raw", ["", "30", "abc", "30y", "-5d", "30 d", "30days"])
def test_parse_duration_invalid(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration(raw)


# ────────────────────── --older-than ──────────────────────


def _seed_session_with_events(db: Any, session_id: str, *, last_event_at: str) -> None:
    db.execute(
        """
        INSERT INTO sessions (
            session_id, worktree_root, cwd, state, last_event_at, started_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, "/tmp/proj", "/tmp/proj", "running", last_event_at, last_event_at),
    )


def test_purge_older_than_deletes_old_rows(
    isolated_paths: Path, keychain_stub: dict[Any, Any]
) -> None:
    db_path = isolated_paths / "support" / "store.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(db_path=db_path)
    now = datetime.now(tz=UTC)
    long_ago = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    _seed_session_with_events(db, "old-sess", last_event_at=long_ago)
    _seed_session_with_events(db, "new-sess", last_event_at=recent)
    db.execute(
        "INSERT INTO events(session_id, event_name, received_at, payload_json) VALUES (?, ?, ?, ?)",
        ("old-sess", "PreToolUse", long_ago, "{}"),
    )
    db.execute(
        "INSERT INTO events(session_id, event_name, received_at, payload_json) VALUES (?, ?, ?, ?)",
        ("new-sess", "PreToolUse", recent, "{}"),
    )
    db.execute(
        "INSERT INTO transcript_messages(session_id, role, timestamp, content_json) "
        "VALUES (?, ?, ?, ?)",
        ("old-sess", "user", long_ago, "{}"),
    )
    db.execute(
        "INSERT INTO transcript_messages(session_id, role, timestamp, content_json) "
        "VALUES (?, ?, ?, ?)",
        ("new-sess", "user", recent, "{}"),
    )
    db.close()

    runner = CliRunner()
    result = runner.invoke(cli_app, ["purge", "--older-than", "30d"])
    assert result.exit_code == 0, result.stdout
    assert "Purged 1 events and 1 transcript messages" in result.stdout

    # Re-open and confirm the row split.
    db = connect(db_path=db_path)
    try:
        evt_old = db.execute(
            "SELECT count(*) FROM events WHERE session_id=?", ("old-sess",)
        ).fetchone()[0]
        evt_new = db.execute(
            "SELECT count(*) FROM events WHERE session_id=?", ("new-sess",)
        ).fetchone()[0]
        msg_old = db.execute(
            "SELECT count(*) FROM transcript_messages WHERE session_id=?", ("old-sess",)
        ).fetchone()[0]
        msg_new = db.execute(
            "SELECT count(*) FROM transcript_messages WHERE session_id=?", ("new-sess",)
        ).fetchone()[0]
    finally:
        db.close()
    assert evt_old == 0
    assert evt_new == 1
    assert msg_old == 0
    assert msg_new == 1


def test_purge_invalid_duration_returns_2(isolated_paths: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["purge", "--older-than", "30years"])
    assert result.exit_code == 2


def test_purge_requires_exactly_one_mode(isolated_paths: Path) -> None:
    runner = CliRunner()
    # Neither set
    result = runner.invoke(cli_app, ["purge"])
    assert result.exit_code == 2
    # Both set
    result = runner.invoke(cli_app, ["purge", "--older-than", "30d", "--reset-passphrase"])
    assert result.exit_code == 2


# ────────────────────── --reset-passphrase ──────────────────────


def test_purge_reset_passphrase_wipes_state(
    isolated_paths: Path, keychain_stub: dict[Any, Any]
) -> None:
    # Seed key in Keychain + a fake DB on disk.
    crypto.store_key_in_keychain(b"\x00" * 32)
    db_path = isolated_paths / "support" / "store.db"
    salt_path = isolated_paths / "support" / "store.salt"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"fake db")
    salt_path.write_bytes(b"fakesalt12345678")

    runner = CliRunner()
    # Confirm prompt with "y"
    result = runner.invoke(cli_app, ["purge", "--reset-passphrase"], input="y\n")
    assert result.exit_code == 0, result.stdout
    assert not db_path.exists()
    assert not salt_path.exists()
    assert crypto.get_key_from_keychain() is None


def test_purge_reset_aborts_on_no(isolated_paths: Path, keychain_stub: dict[Any, Any]) -> None:
    crypto.store_key_in_keychain(b"\x00" * 32)
    runner = CliRunner()
    result = runner.invoke(cli_app, ["purge", "--reset-passphrase"], input="n\n")
    assert result.exit_code == 1
    # Key still present.
    assert crypto.get_key_from_keychain() is not None
