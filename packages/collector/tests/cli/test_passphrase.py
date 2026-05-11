"""End-to-end passphrase rotation via the CLI.

Uses ``FAST_KDF`` so the test runs in <1s. The real ``crypto.first_run_setup``
and ``rotate_passphrase`` are exercised — only ``keyring`` is stubbed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sqlcipher3
from typer.testing import CliRunner

from csm import crypto
from csm.cli import app as cli_app
from csm.crypto import KdfParams, derive_key, first_run_setup, get_key_from_keychain
from csm.db import connect

FAST_KDF = KdfParams(time_cost=1, memory_cost=8, parallelism=1, hash_len=32)


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


def _seed_db(passphrase: str, salt_path: Path, db_path: Path) -> bytes:
    """Run first_run_setup + insert a marker row so we can detect rekey loss."""
    key = first_run_setup(passphrase, salt_path, params=FAST_KDF)
    conn = connect(key=key, db_path=db_path)
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("test_marker", "preserved"),
        )
    finally:
        conn.close()
    return key


def test_change_passphrase_round_trip(
    isolated_paths: Path,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: install, then rotate, then re-open with the new key."""
    salt_path = isolated_paths / "support" / "store.salt"
    db_path = isolated_paths / "support" / "store.db"
    salt_path.parent.mkdir(parents=True, exist_ok=True)

    old_key = _seed_db("alpha-passphrase", salt_path, db_path)

    # Force the CLI's rotate to use FAST_KDF so the test stays under a
    # second. The CLI itself doesn't take params; we patch the default
    # at the call site.
    real_rotate = crypto.rotate_passphrase

    def fast_rotate(*args: Any, **kwargs: Any) -> bytes:
        kwargs["params"] = FAST_KDF
        return real_rotate(*args, **kwargs)

    monkeypatch.setattr("csm.cli.passphrase.crypto.rotate_passphrase", fast_rotate)

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        ["change-passphrase"],
        input="alpha-passphrase\nbravo-passphrase\nbravo-passphrase\n",
    )
    assert result.exit_code == 0, result.stdout
    assert "rotated" in result.stdout.lower()

    new_key = get_key_from_keychain()
    assert new_key is not None
    assert new_key != old_key

    # Old key must fail.
    with pytest.raises(sqlcipher3.DatabaseError):
        connect(key=old_key, db_path=db_path)

    # New key opens cleanly and the marker row is intact.
    conn = connect(key=new_key, db_path=db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", ("test_marker",)).fetchone()
    finally:
        conn.close()
    assert row[0] == "preserved"


def test_change_passphrase_wrong_old_passphrase(
    isolated_paths: Path,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrong old passphrase yields exit code 1 and a clean error message."""
    salt_path = isolated_paths / "support" / "store.salt"
    db_path = isolated_paths / "support" / "store.db"
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    _seed_db("alpha-passphrase", salt_path, db_path)

    real_rotate = crypto.rotate_passphrase

    def fast_rotate(*args: Any, **kwargs: Any) -> bytes:
        kwargs["params"] = FAST_KDF
        return real_rotate(*args, **kwargs)

    monkeypatch.setattr("csm.cli.passphrase.crypto.rotate_passphrase", fast_rotate)

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        ["change-passphrase"],
        input="WRONG-passphrase\nbravo-passphrase\nbravo-passphrase\n",
    )
    assert result.exit_code == 1
    # Existing key in Keychain is unchanged.
    salt = salt_path.read_bytes()
    expected_key = derive_key("alpha-passphrase", salt, FAST_KDF)
    assert get_key_from_keychain() == expected_key


def test_change_passphrase_rejects_short_new_passphrase(
    isolated_paths: Path,
    keychain_stub: dict[Any, Any],
) -> None:
    """A new passphrase shorter than MIN_PASSPHRASE_LEN must be rejected
    before any rekey attempt — exit code 2, no Keychain mutation."""
    salt_path = isolated_paths / "support" / "store.salt"
    db_path = isolated_paths / "support" / "store.db"
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    _seed_db("alpha-passphrase", salt_path, db_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        ["change-passphrase"],
        input="alpha-passphrase\nshort\nshort\n",
    )
    assert result.exit_code == 2
    # Keychain still holds the original key.
    salt = salt_path.read_bytes()
    expected_key = derive_key("alpha-passphrase", salt, FAST_KDF)
    assert get_key_from_keychain() == expected_key
