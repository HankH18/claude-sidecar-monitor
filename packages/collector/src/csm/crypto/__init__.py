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
from typing import Any

import keyring
import keyring.errors
from argon2.low_level import Type, hash_secret_raw

from csm.config import KEYCHAIN_SERVICE
from csm.db import connect, hex_key

__all__ = [
    "DEFAULT_KDF",
    "MIN_PASSPHRASE_LEN",
    "KdfParams",
    "delete_key_from_keychain",
    "derive_key",
    "first_run_setup",
    "get_key_from_keychain",
    "load_or_create_salt",
    "recover_from_pending_rotation",
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

# Minimum passphrase length. Argon2id will happily derive a 32-byte key
# from any non-empty string, but a 0- or 1-character passphrase makes the
# resulting "encryption" trivially brute-forceable while leaving the user
# with false confidence. The CLI install + change-passphrase paths both
# enforce this floor up front. Tests can override via direct
# ``derive_key()`` calls (which bypass this constant).
MIN_PASSPHRASE_LEN = 8


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


# ────────────────────── pending-rotation crash recovery ──────────────────────
# Passphrase rotation has three discrete steps (write pending key, PRAGMA
# rekey, swap primary key) and process death between any two leaves the
# system in a recoverable but inconsistent state. We stash the new key under
# a SECONDARY Keychain account during rotation so startup can detect a
# half-rotated state and roll the system forward (or back) deterministically.

_PENDING_SUFFIX = ".pending-rotation"


def _pending_account() -> str:
    return _account() + _PENDING_SUFFIX


def _store_pending_key(key: bytes) -> None:
    if len(key) != 32:
        raise ValueError(f"expected 32-byte key, got {len(key)} bytes")
    keyring.set_password(KEYCHAIN_SERVICE, _pending_account(), hex_key(key))


def _get_pending_key() -> bytes | None:
    raw = keyring.get_password(KEYCHAIN_SERVICE, _pending_account())
    return bytes.fromhex(raw) if raw is not None else None


def _delete_pending_key() -> None:
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(KEYCHAIN_SERVICE, _pending_account())


def recover_from_pending_rotation(db_path: Path) -> bytes | None:
    """If a pending-rotation Keychain entry is present, figure out which key
    actually opens the DB (primary or pending) and clean up.

    Returns the working key (the one to pass to ``connect``), or ``None``
    if neither key works (genuine data loss — caller should surface a
    clear error and direct the user to ``csm purge --reset-passphrase``).

    Safe to call on every startup; the no-pending-entry fast path is a
    single Keychain read.
    """
    primary = get_key_from_keychain()
    pending = _get_pending_key()
    if pending is None:
        return primary  # No rotation in progress — fast path.

    # Case 1: primary opens. Pending was orphaned (rotation died BEFORE
    # rekey actually mutated the DB). Roll forward by deleting pending.
    if primary is not None:
        try:
            conn = _try_open(db_path, primary)
        except Exception:
            conn = None
        if conn is not None:
            conn.close()
            _delete_pending_key()
            return primary

    # Case 2: pending opens. rekey ran but the primary-entry update didn't.
    # Promote pending to primary, then clear it.
    try:
        conn = _try_open(db_path, pending)
    except Exception:
        conn = None
    if conn is not None:
        conn.close()
        store_key_in_keychain(pending)
        _delete_pending_key()
        return pending

    # Neither key works. Pending is bookkeeping; do NOT delete it
    # (a future doctor invocation needs to see something is wrong).
    return None


def _try_open(db_path: Path, key: bytes) -> Any:
    """Open with the given key. Raises on wrong-key. Avoids module-cycle by
    importing db.connect lazily — crypto.connect would be circular."""
    from csm.db import connect

    return connect(key=key, db_path=db_path, apply_migrations_on_open=False)


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

    Crash-recovery sequence (see ``recover_from_pending_rotation``):

    1. Stash the new key under a transient ``.pending-rotation`` Keychain
       entry. If we die before step 2, primary still opens the DB; recovery
       deletes the orphan pending entry.
    2. ``PRAGMA rekey`` the DB to the new key. If we die between step 2 and
       step 3, primary fails to open but pending opens; recovery promotes
       pending and deletes it.
    3. Promote: write the new key to the primary Keychain entry, then delete
       the pending entry. Either order leaves a recoverable state.

    If ``PRAGMA rekey`` itself raises, the DB hasn't been mutated (SQLCipher
    is atomic); we delete the pending entry and re-raise so the CLI shows
    a clean wrong-passphrase error.
    """
    salt = load_or_create_salt(salt_path)
    old_key = derive_key(old_passphrase, salt, params)
    new_key = derive_key(new_passphrase, salt, params)

    # Step 1 — stash pending.
    _store_pending_key(new_key)
    try:
        # Step 2 — rekey.
        conn = connect(key=old_key, db_path=db_path, apply_migrations_on_open=False)
        try:
            conn.execute(f"PRAGMA rekey = \"x'{hex_key(new_key)}'\"")
        finally:
            conn.close()
    except Exception:
        # rekey failed — DB is still encrypted with old_key (atomic per
        # SQLCipher). Clear the pending entry so the next start doesn't see
        # a stale rotation marker, and re-raise.
        _delete_pending_key()
        raise

    # Step 3 — promote, then clear pending.
    store_key_in_keychain(new_key)
    _delete_pending_key()
    return new_key
