"""At-rest encryption — Argon2id KDF + macOS Keychain caching.

Public surface:

- ``KdfParams`` — Argon2id parameter bundle (production defaults are
  the canonical values; tests can override).
- ``derive_key(passphrase, salt, params=...)`` — passphrase → 32-byte key.
- ``load_or_create_salt(salt_path)`` — per-install random 16-byte salt.
- ``get_key_from_keychain() / store_key_in_keychain(key)`` —
  macOS Keychain via ``keyring``, service ``claude-sidecar-monitor``.
- ``first_run_setup(passphrase, salt_path)`` — derive key, persist salt,
  cache key in Keychain. Returns the derived key.
- ``rotate_passphrase(old, new, salt_path, db_path)`` — atomic rekey.

**Audit safety: nothing in this module logs the passphrase or the
derived key.**
"""

from __future__ import annotations

import contextlib
import getpass
import secrets
from dataclasses import dataclass
from pathlib import Path

import keyring
import keyring.errors
from argon2.low_level import Type, hash_secret_raw

from csm.config import KEYCHAIN_SERVICE
from csm.db import connect, hex_key

__all__ = [
    "DEFAULT_KDF",
    "KdfParams",
    "derive_key",
    "first_run_setup",
    "get_key_from_keychain",
    "load_or_create_salt",
    "rotate_passphrase",
    "store_key_in_keychain",
]


@dataclass(frozen=True)
class KdfParams:
    """Argon2id parameters. Production defaults match docs/spec.md §2.

    Memory cost is in KiB. ``time_cost=3`` x ``memory_cost=64*1024``
    x ``parallelism=4`` ~= 200 ms on Apple Silicon.
    """

    time_cost: int
    memory_cost: int
    parallelism: int
    hash_len: int = 32


DEFAULT_KDF = KdfParams(time_cost=3, memory_cost=64 * 1024, parallelism=4)


def derive_key(
    passphrase: str,
    salt: bytes,
    params: KdfParams = DEFAULT_KDF,
) -> bytes:
    """Derive a 32-byte SQLCipher key from a passphrase and salt."""
    if len(salt) < 8:
        raise ValueError("salt must be ≥8 bytes")
    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost,
        parallelism=params.parallelism,
        hash_len=params.hash_len,
        type=Type.ID,
    )


def load_or_create_salt(salt_path: Path) -> bytes:
    """Return the per-install salt, generating it if missing.

    Mode is forced to 0600 every call so a permissions drift on the
    salt file gets corrected next start-up.
    """
    if salt_path.exists():
        salt = salt_path.read_bytes()
        salt_path.chmod(0o600)
        return salt
    salt_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    salt = secrets.token_bytes(16)
    salt_path.write_bytes(salt)
    salt_path.chmod(0o600)
    return salt


def _account() -> str:
    return getpass.getuser()


def get_key_from_keychain() -> bytes | None:
    raw = keyring.get_password(KEYCHAIN_SERVICE, _account())
    if raw is None:
        return None
    return bytes.fromhex(raw)


def store_key_in_keychain(key: bytes) -> None:
    if len(key) != 32:
        raise ValueError(f"expected 32-byte key, got {len(key)} bytes")
    keyring.set_password(KEYCHAIN_SERVICE, _account(), hex_key(key))


def delete_key_from_keychain() -> None:
    """Remove the cached key. Used by ``csm uninstall --purge``."""
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(KEYCHAIN_SERVICE, _account())


def first_run_setup(
    passphrase: str,
    salt_path: Path,
    *,
    params: KdfParams = DEFAULT_KDF,
) -> bytes:
    """Derive the key from passphrase+salt, cache in Keychain, return it."""
    salt = load_or_create_salt(salt_path)
    key = derive_key(passphrase, salt, params)
    store_key_in_keychain(key)
    return key


def rotate_passphrase(
    old_passphrase: str,
    new_passphrase: str,
    *,
    salt_path: Path,
    db_path: Path,
    params: KdfParams = DEFAULT_KDF,
) -> bytes:
    """Open the DB with the old key, ``PRAGMA rekey`` to the new key,
    update Keychain. Returns the new raw key.

    SQLCipher 4 ``PRAGMA rekey`` rewrites every page atomically with the
    new key; if the old passphrase is wrong, the open itself will fail
    before any write happens. The DB connection is closed before
    returning so callers don't accidentally hold a stale handle.
    """
    salt = load_or_create_salt(salt_path)
    old_key = derive_key(old_passphrase, salt, params)
    new_key = derive_key(new_passphrase, salt, params)

    conn = connect(key=old_key, db_path=db_path, apply_migrations_on_open=False)
    try:
        conn.execute(f"PRAGMA rekey = \"x'{hex_key(new_key)}'\"")
    finally:
        conn.close()

    store_key_in_keychain(new_key)
    return new_key
