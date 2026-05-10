"""Crypto module tests — KDF, salt, Keychain, rotation.

The Keychain tests stub ``keyring`` with an in-memory dict so we never
touch the user's actual macOS Keychain during testing.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import pytest
import sqlcipher3

from csm import crypto
from csm.crypto import (
    DEFAULT_KDF,
    KdfParams,
    delete_key_from_keychain,
    derive_key,
    first_run_setup,
    get_key_from_keychain,
    load_or_create_salt,
    rotate_passphrase,
    store_key_in_keychain,
)
from csm.db import connect

# Cheap KDF for tests that don't need the full 64-MB Argon2 cost.
FAST_KDF = KdfParams(time_cost=1, memory_cost=8, parallelism=1, hash_len=32)


@pytest.fixture
def keychain_stub(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    """Replace ``keyring`` with an in-memory dict for the duration of the test."""
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


# ────────── KDF ──────────


def test_kdf_deterministic_for_same_input() -> None:
    salt = b"sixteen-byte-salt"
    a = derive_key("hunter2", salt, FAST_KDF)
    b = derive_key("hunter2", salt, FAST_KDF)
    assert a == b
    assert len(a) == 32


def test_kdf_different_passphrase_different_key() -> None:
    salt = b"sixteen-byte-salt"
    assert derive_key("a", salt, FAST_KDF) != derive_key("b", salt, FAST_KDF)


def test_kdf_different_salt_different_key() -> None:
    a = derive_key("p", b"salt-a-aaaaaaaaa", FAST_KDF)
    b = derive_key("p", b"salt-b-bbbbbbbbb", FAST_KDF)
    assert a != b


def test_kdf_rejects_short_salt() -> None:
    with pytest.raises(ValueError, match="salt must be"):
        derive_key("p", b"short", FAST_KDF)


def test_default_kdf_params_documented() -> None:
    """Sanity: production parameters match docs/spec.md §2."""
    assert DEFAULT_KDF.time_cost == 3
    assert DEFAULT_KDF.memory_cost == 64 * 1024
    assert DEFAULT_KDF.parallelism == 4
    assert DEFAULT_KDF.hash_len == 32


# ────────── Salt ──────────


def test_salt_is_created_on_first_call(tmp_path: Path) -> None:
    salt_path = tmp_path / "store.salt"
    salt = load_or_create_salt(salt_path)
    assert salt_path.exists()
    assert len(salt) == 16


def test_salt_is_stable_across_calls(tmp_path: Path) -> None:
    salt_path = tmp_path / "store.salt"
    a = load_or_create_salt(salt_path)
    b = load_or_create_salt(salt_path)
    assert a == b


def test_salt_file_mode_is_0600(tmp_path: Path) -> None:
    salt_path = tmp_path / "store.salt"
    load_or_create_salt(salt_path)
    mode = salt_path.stat().st_mode & 0o777
    assert mode == 0o600


# ────────── Keychain ──────────


def test_keychain_miss_returns_none(keychain_stub: dict[Any, Any]) -> None:
    assert get_key_from_keychain() is None


def test_keychain_round_trip(keychain_stub: dict[Any, Any]) -> None:
    key = secrets.token_bytes(32)
    store_key_in_keychain(key)
    assert get_key_from_keychain() == key


def test_keychain_rejects_short_key(keychain_stub: dict[Any, Any]) -> None:
    with pytest.raises(ValueError, match="32-byte key"):
        store_key_in_keychain(b"too short")


def test_keychain_delete(keychain_stub: dict[Any, Any]) -> None:
    store_key_in_keychain(secrets.token_bytes(32))
    delete_key_from_keychain()
    assert get_key_from_keychain() is None
    # Idempotent — deleting a missing entry is fine.
    delete_key_from_keychain()


# ────────── End-to-end ──────────


def test_first_run_setup_caches_key(tmp_path: Path, keychain_stub: dict[Any, Any]) -> None:
    salt_path = tmp_path / "store.salt"
    key = first_run_setup("correct horse battery staple", salt_path, params=FAST_KDF)
    assert len(key) == 32
    assert get_key_from_keychain() == key


def test_rotation_round_trip(tmp_path: Path, keychain_stub: dict[Any, Any]) -> None:
    salt_path = tmp_path / "store.salt"
    db_path = tmp_path / "store.db"

    # First-run setup with passphrase A
    key_a = first_run_setup("alpha", salt_path, params=FAST_KDF)
    conn = connect(key=key_a, db_path=db_path)
    try:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("rotated", "yes"))
    finally:
        conn.close()

    # Rotate to passphrase B
    key_b = rotate_passphrase(
        "alpha", "bravo", salt_path=salt_path, db_path=db_path, params=FAST_KDF
    )
    assert key_b != key_a
    assert get_key_from_keychain() == key_b

    # Reading with new key works
    conn_b = connect(key=key_b, db_path=db_path)
    try:
        value = conn_b.execute("SELECT value FROM settings WHERE key=?", ("rotated",)).fetchone()[0]
    finally:
        conn_b.close()
    assert value == "yes"

    # Reading with old key fails
    with pytest.raises(sqlcipher3.DatabaseError):
        connect(key=key_a, db_path=db_path)
