"""Tests for the install-command key-setup routing.

The install command must never blindly overwrite a working Keychain entry
— previously it always prompted for a new passphrase and re-derived the
key, which stranded users whose new passphrase didn't match the DB.

These tests exercise the three branches in ``_setup_or_reuse_key``:
- existing key + DB opens → reuse, no prompt
- existing key + DB doesn't open → recovery prompt, verify before write
- no key OR no DB → fresh prompt
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from csm import crypto
from csm.cli import app as cli_app
from csm.cli import install as install_mod
from csm.cli.install import _can_open_db, _setup_or_reuse_key
from csm.config import Paths
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
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    """Point all path-resolving env vars at tmp_path."""
    monkeypatch.setenv("CSM_APP_SUPPORT", str(tmp_path / "support"))
    monkeypatch.setenv("CSM_DB_PATH", str(tmp_path / "support" / "store.db"))
    monkeypatch.setenv("CSM_SALT_PATH", str(tmp_path / "support" / "store.salt"))
    monkeypatch.setenv("CSM_LOG_DIR", str(tmp_path / "logs"))
    (tmp_path / "support").mkdir(parents=True, exist_ok=True)
    return Paths.from_env()


def _seed_real_db(paths: Paths, passphrase: str = "correct-horse-battery-staple") -> bytes:
    """Run the real first_run_setup so the DB is encrypted with a real key."""
    crypto.first_run_setup(passphrase, paths.salt)
    key = crypto.get_key_from_keychain()
    assert key is not None
    conn = connect(key=key, db_path=paths.db)
    conn.close()
    return key


# ────────────────────── _can_open_db ──────────────────────


def test_can_open_db_returns_false_for_missing_file(isolated_paths: Paths) -> None:
    # No DB has been created yet.
    assert _can_open_db(b"\x00" * 32, isolated_paths.db) is False


def test_can_open_db_returns_true_for_matching_key(
    isolated_paths: Paths, keychain_stub: dict[Any, Any]
) -> None:
    real_key = _seed_real_db(isolated_paths)
    assert _can_open_db(real_key, isolated_paths.db) is True


def test_can_open_db_returns_false_for_wrong_key(
    isolated_paths: Paths, keychain_stub: dict[Any, Any]
) -> None:
    _seed_real_db(isolated_paths)
    wrong = b"\x01" * 32
    assert _can_open_db(wrong, isolated_paths.db) is False


# ────────────────────── _setup_or_reuse_key — reuse branch ──────────────────────


def test_setup_or_reuse_key_reuses_when_cache_opens_db(
    isolated_paths: Paths, keychain_stub: dict[Any, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """Happy re-install: cached key still works, no passphrase prompt."""
    real_key = _seed_real_db(isolated_paths)
    # No stdin provided — if the function prompts, the test will hang
    # rather than silently passing.
    result = _setup_or_reuse_key(isolated_paths)
    assert result == real_key
    captured = capsys.readouterr()
    assert "reusing" in captured.out.lower()


# ────────────────────── _setup_or_reuse_key — recovery branch ──────────────────────


def test_setup_or_reuse_key_recovery_prompt_with_correct_passphrase(
    isolated_paths: Paths,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB encrypted with passphrase X, Keychain has key from passphrase Y.
    User re-enters X at the recovery prompt — Keychain gets updated to the
    correct key, DB now opens.
    """
    real_passphrase = "correct-horse-battery-staple"
    real_key = _seed_real_db(isolated_paths, passphrase=real_passphrase)

    # Simulate the bug: someone called first_run_setup with a different
    # passphrase, which overwrote the Keychain entry with a wrong key.
    # We do that by directly stashing a fabricated key.
    crypto.store_key_in_keychain(b"\x02" * 32)
    assert crypto.get_key_from_keychain() != real_key

    # Drive the typer prompts: confirm + correct passphrase.
    inputs = iter(["y", real_passphrase])
    monkeypatch.setattr(install_mod.typer, "confirm", lambda *_a, **_k: True)
    monkeypatch.setattr(install_mod.typer, "prompt", lambda *_a, **_k: next(inputs))

    result = _setup_or_reuse_key(isolated_paths)
    assert result == real_key
    # Keychain was repaired with the correct key.
    assert crypto.get_key_from_keychain() == real_key


def test_setup_or_reuse_key_recovery_fails_after_three_wrong_attempts(
    isolated_paths: Paths,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_real_db(isolated_paths, passphrase="correct-horse-battery-staple")
    crypto.store_key_in_keychain(b"\x02" * 32)

    monkeypatch.setattr(install_mod.typer, "confirm", lambda *_a, **_k: True)
    monkeypatch.setattr(
        install_mod.typer, "prompt", lambda *_a, **_k: "wrongpassword-but-long-enough"
    )

    with pytest.raises(typer.Exit) as exc_info:
        _setup_or_reuse_key(isolated_paths)
    assert exc_info.value.exit_code == 1


def test_setup_or_reuse_key_recovery_does_not_overwrite_keychain_on_failure(
    isolated_paths: Paths,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If recovery fails, the (wrong) Keychain entry is left untouched —
    no further damage. The user can re-attempt or purge."""
    _seed_real_db(isolated_paths, passphrase="correct-horse-battery-staple")
    bad_key = b"\x02" * 32
    crypto.store_key_in_keychain(bad_key)

    monkeypatch.setattr(install_mod.typer, "confirm", lambda *_a, **_k: True)
    monkeypatch.setattr(install_mod.typer, "prompt", lambda *_a, **_k: "alsoincorrect-but-long")

    with pytest.raises(typer.Exit):
        _setup_or_reuse_key(isolated_paths)

    # The wrong key is still there — we didn't make it worse.
    assert crypto.get_key_from_keychain() == bad_key


def test_setup_or_reuse_key_recovery_aborted_on_no(
    isolated_paths: Paths,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_real_db(isolated_paths, passphrase="correct-horse-battery-staple")
    crypto.store_key_in_keychain(b"\x02" * 32)

    monkeypatch.setattr(install_mod.typer, "confirm", lambda *_a, **_k: False)

    with pytest.raises(typer.Exit) as exc_info:
        _setup_or_reuse_key(isolated_paths)
    assert exc_info.value.exit_code == 1


# ────────────────────── _setup_or_reuse_key — fresh-install branch ──────────────────────


def test_setup_or_reuse_key_first_run_prompts_for_new_passphrase(
    isolated_paths: Paths,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty Keychain + no DB → standard first-run."""
    monkeypatch.setattr(install_mod.typer, "prompt", lambda *_a, **_k: "fresh-passphrase-here")

    key = _setup_or_reuse_key(isolated_paths)
    # The newly-stored Keychain key matches.
    assert key == crypto.get_key_from_keychain()
    # _setup_or_reuse_key doesn't materialize the DB itself — the caller's
    # next step (api_secret INSERT) opens it. Open it here ourselves to
    # verify the cached key actually works.
    conn = connect(key=key, db_path=isolated_paths.db)
    conn.close()
    assert _can_open_db(key, isolated_paths.db)


def test_setup_or_reuse_key_clears_stale_entry_when_db_missing(
    isolated_paths: Paths,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keychain entry from a previous install, but DB was nuked out of band.
    Clear the stale entry and prompt fresh."""
    crypto.store_key_in_keychain(b"\x05" * 32)
    assert isolated_paths.db.exists() is False

    monkeypatch.setattr(install_mod.typer, "prompt", lambda *_a, **_k: "fresh-after-cleanup")

    key = _setup_or_reuse_key(isolated_paths)
    assert key == crypto.get_key_from_keychain()
    captured = capsys.readouterr()
    assert "stale" in captured.out.lower()


# ────────────────────── purge UX (no-args message) ──────────────────────


def test_purge_no_args_prints_helpful_usage() -> None:
    """`csm purge` (no args) must explain BOTH flags, not just say
    'pass exactly one of...'."""
    runner = CliRunner()
    result = runner.invoke(cli_app, ["purge"])
    assert result.exit_code == 2
    combined = result.stdout + (result.stderr or "")
    assert "--older-than" in combined
    assert "--reset-passphrase" in combined
    # Make sure we surface a concrete example so the user knows the
    # duration grammar without reading --help.
    assert "30d" in combined


def test_purge_both_flags_explains_mutex() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["purge", "--older-than", "30d", "--reset-passphrase"])
    assert result.exit_code == 2
    combined = result.stdout + (result.stderr or "")
    assert "mutually exclusive" in combined.lower()
