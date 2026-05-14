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


# ────────── pending-rotation recovery ──────────


def test_recover_no_pending_returns_primary(tmp_path, keychain_stub) -> None:
    """The fast path: no rotation in progress → just return what's in
    Keychain (or None)."""
    from csm.crypto import recover_from_pending_rotation

    salt_path = tmp_path / "store.salt"
    db_path = tmp_path / "store.db"

    # Empty Keychain.
    assert recover_from_pending_rotation(db_path) is None

    # Primary present, no pending.
    key = first_run_setup("alpha-passphrase", salt_path, params=FAST_KDF)
    # Ensure DB exists so a future open attempt would be possible.
    connect(key=key, db_path=db_path).close()
    assert recover_from_pending_rotation(db_path) == key


def test_recover_orphan_pending_when_rekey_never_happened(tmp_path, keychain_stub) -> None:
    """Process died after step 1 (pending stash) but before step 2 (rekey):
    primary still opens the DB, so recovery deletes the orphan pending."""
    from csm.crypto import _store_pending_key, recover_from_pending_rotation

    salt_path = tmp_path / "store.salt"
    db_path = tmp_path / "store.db"
    key = first_run_setup("alpha-passphrase", salt_path, params=FAST_KDF)
    connect(key=key, db_path=db_path).close()

    # Simulate the half-rotation: write a pending entry that doesn't match
    # the DB's actual encryption key.
    _store_pending_key(secrets.token_bytes(32))

    recovered = recover_from_pending_rotation(db_path)
    assert recovered == key
    # Pending was cleaned up.
    from csm.crypto import _get_pending_key

    assert _get_pending_key() is None


def test_recover_promotes_pending_when_rekey_succeeded(tmp_path, keychain_stub) -> None:
    """Process died after step 2 (rekey ran) but before step 3 (primary
    update): primary fails to open, pending opens. Recovery promotes
    pending → primary and clears it."""
    from csm.crypto import (
        _delete_pending_key,
        _get_pending_key,
        _store_pending_key,
        recover_from_pending_rotation,
    )

    salt_path = tmp_path / "store.salt"
    db_path = tmp_path / "store.db"

    # Initial state: primary key opens the DB.
    key_a = first_run_setup("alpha-passphrase", salt_path, params=FAST_KDF)
    connect(key=key_a, db_path=db_path).close()

    # Simulate a successful rekey to key_b without the primary-entry update.
    key_b = secrets.token_bytes(32)
    conn = connect(key=key_a, db_path=db_path, apply_migrations_on_open=False)
    try:
        conn.execute(f"PRAGMA rekey = \"x'{key_b.hex()}'\"")
    finally:
        conn.close()
    # Primary still points at key_a (stale), pending at key_b.
    _store_pending_key(key_b)

    recovered = recover_from_pending_rotation(db_path)
    assert recovered == key_b
    assert get_key_from_keychain() == key_b
    assert _get_pending_key() is None

    # Cleanup for clarity (already deleted, but double-confirm).
    _delete_pending_key()


def test_recover_returns_none_when_neither_key_works(tmp_path, keychain_stub) -> None:
    """Both primary and pending are wrong (deeply broken Keychain state):
    return None and leave pending in place for diagnostic visibility."""
    from csm.crypto import _get_pending_key, _store_pending_key, recover_from_pending_rotation

    salt_path = tmp_path / "store.salt"
    db_path = tmp_path / "store.db"
    real_key = first_run_setup("alpha-passphrase", salt_path, params=FAST_KDF)
    connect(key=real_key, db_path=db_path).close()

    # Now stomp both Keychain entries with garbage.
    store_key_in_keychain(secrets.token_bytes(32))
    _store_pending_key(secrets.token_bytes(32))

    assert recover_from_pending_rotation(db_path) is None
    # Pending NOT cleaned up — diagnostic value.
    assert _get_pending_key() is not None


def test_rotation_cleans_pending_on_success(tmp_path, keychain_stub) -> None:
    """The normal successful rotation path leaves NO pending entry."""
    from csm.crypto import _get_pending_key

    salt_path = tmp_path / "store.salt"
    db_path = tmp_path / "store.db"
    first_run_setup("alpha-passphrase", salt_path, params=FAST_KDF)
    connect(key=get_key_from_keychain(), db_path=db_path).close()  # type: ignore[arg-type]

    rotate_passphrase(
        "alpha-passphrase",
        "bravo-passphrase",
        salt_path=salt_path,
        db_path=db_path,
        params=FAST_KDF,
    )
    assert _get_pending_key() is None


def test_rotation_clears_pending_on_failure(tmp_path, keychain_stub) -> None:
    """If the rekey raises, pending must be cleaned up and the original
    primary key must remain untouched."""
    from csm.crypto import _get_pending_key

    salt_path = tmp_path / "store.salt"
    db_path = tmp_path / "store.db"
    original = first_run_setup("alpha-passphrase", salt_path, params=FAST_KDF)
    connect(key=original, db_path=db_path).close()

    with pytest.raises(sqlcipher3.DatabaseError):
        rotate_passphrase(
            "WRONG-passphrase",  # wrong old → connect raises
            "bravo-passphrase",
            salt_path=salt_path,
            db_path=db_path,
            params=FAST_KDF,
        )
    assert _get_pending_key() is None
    assert get_key_from_keychain() == original
