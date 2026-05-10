"""Tests for ``csm doctor`` diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from csm import crypto
from csm.cli import app as cli_app
from csm.cli.doctor import (
    _check_collector_reachable,
    _check_hooks_installed,
    _check_launchd_plist,
    _check_ntfy_topic_set,
    _check_sqlcipher,
)
from csm.cli.hooks import install_hooks
from csm.db import connect


@pytest.fixture
def keychain_stub(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        crypto.keyring,
        "set_password",
        lambda s, a, p: store.__setitem__((s, a), p),
    )
    monkeypatch.setattr(crypto.keyring, "get_password", lambda s, a: store.get((s, a)))

    def _delete(s: str, a: str) -> None:
        if (s, a) not in store:
            import keyring.errors

            raise keyring.errors.PasswordDeleteError("not found")
        del store[(s, a)]

    monkeypatch.setattr(crypto.keyring, "delete_password", _delete)
    return store


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CSM_APP_SUPPORT", str(tmp_path / "support"))
    monkeypatch.setenv("CSM_DB_PATH", str(tmp_path / "support" / "store.db"))
    monkeypatch.setenv("CSM_SALT_PATH", str(tmp_path / "support" / "store.salt"))
    monkeypatch.setenv("CSM_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CSM_CLAUDE_SETTINGS", str(tmp_path / "claude-settings.json"))
    return tmp_path


# ────────────────────── individual checks ──────────────────────


def test_hooks_check_missing(tmp_path: Path) -> None:
    settings = tmp_path / "missing.json"
    script = tmp_path / "csm-hook.sh"
    result = _check_hooks_installed(settings, script)
    assert result.ok is False
    assert "does not exist" in result.detail


def test_hooks_check_invalid_json(tmp_path: Path) -> None:
    settings = tmp_path / "broken.json"
    settings.write_text("not json {")
    result = _check_hooks_installed(settings, tmp_path / "csm-hook.sh")
    assert result.ok is False
    assert "not valid JSON" in result.detail


def test_hooks_check_missing_events(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {}}))
    result = _check_hooks_installed(settings, tmp_path / "csm-hook.sh")
    assert result.ok is False
    assert "missing entries" in result.detail


def test_hooks_check_passes_after_install(isolated_paths: Path) -> None:
    settings = isolated_paths / "claude-settings.json"
    script = isolated_paths / "csm-hook.sh"
    install_hooks(settings_path=settings, script_path=script)
    result = _check_hooks_installed(settings, script)
    assert result.ok is True


def test_launchd_check_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = _check_launchd_plist()
    assert result.ok is False


def test_launchd_check_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    p = tmp_path / "Library" / "LaunchAgents" / "com.hank.claude-sidecar-monitor.plist"
    p.parent.mkdir(parents=True)
    p.write_text("<plist/>")
    result = _check_launchd_plist()
    assert result.ok is True


def test_collector_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **_: Any) -> Any:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = _check_collector_reachable()
    assert result.ok is False
    assert "ConnectError" in result.detail


def test_collector_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 200

    def fake_get(url: str, **_: Any) -> FakeResp:
        return FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    result = _check_collector_reachable()
    assert result.ok is True


def test_sqlcipher_check_passes() -> None:
    """Always passes in the test env — sqlcipher3 is a hard dep."""
    result = _check_sqlcipher()
    assert result.ok is True


def test_ntfy_topic_check_no_db(isolated_paths: Path) -> None:
    result = _check_ntfy_topic_set(key=None)
    assert result.ok is False
    assert "DB does not exist" in result.detail


def test_ntfy_topic_check_empty(isolated_paths: Path) -> None:
    db_path = isolated_paths / "support" / "store.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(db_path=db_path)
    db.close()
    result = _check_ntfy_topic_set(key=None)
    assert result.ok is False  # default is empty


def test_ntfy_topic_check_set(isolated_paths: Path) -> None:
    db_path = isolated_paths / "support" / "store.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(db_path=db_path)
    db.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("ntfy_topic", "csm-test-topic"),
    )
    db.close()
    result = _check_ntfy_topic_set(key=None)
    assert result.ok is True
    assert result.detail == "csm-test-topic"


# ────────────────────── full doctor command ──────────────────────


def test_doctor_command_reports_failures(
    isolated_paths: Path,
    keychain_stub: dict[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pristine env (no install) should fail several checks but exit cleanly."""
    monkeypatch.setenv("HOME", str(isolated_paths))

    def fake_get(url: str, **_: Any) -> Any:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", fake_get)

    runner = CliRunner()
    result = runner.invoke(cli_app, ["doctor"])
    assert result.exit_code == 1
    assert "csm doctor" in result.stdout
    # At least one failed check is shown.
    assert "[x ]" in result.stdout
