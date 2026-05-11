"""Tests for ``csm install-hooks`` JSON-merge / backup / idempotency logic.

All tests use ``tmp_path`` and ``monkeypatch.setenv("CSM_CLAUDE_SETTINGS", ...)``
so the user's real ``~/.claude/settings.json`` is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from csm.cli import app as cli_app
from csm.cli._hook_script import HOOK_SCRIPT
from csm.cli.hooks import (
    HOOK_EVENTS,
    install_hooks,
)


@pytest.fixture
def settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "claude-settings.json"
    monkeypatch.setenv("CSM_CLAUDE_SETTINGS", str(p))
    return p


@pytest.fixture
def script_path(tmp_path: Path) -> Path:
    return tmp_path / ".csm" / "csm-hook.sh"


# ────────────────────── basic install / shape ──────────────────────


def test_install_creates_settings_when_missing(settings_path: Path, script_path: Path) -> None:
    """Fresh install writes a brand-new settings.json with all hook entries."""
    assert not settings_path.exists()

    result = install_hooks(settings_path=settings_path, script_path=script_path)

    assert result.changed is True
    assert result.backup_path is None  # no prior file = nothing to back up
    data = json.loads(settings_path.read_text())
    for ev in HOOK_EVENTS:
        block = data["hooks"][ev]
        assert isinstance(block, list)
        assert len(block) == 1
        cmd = block[0]["hooks"][0]["command"]
        assert cmd == f"{script_path} {ev}"
        assert block[0]["hooks"][0]["type"] == "command"
        assert block[0]["matcher"] == ""


def test_install_writes_hook_script(settings_path: Path, script_path: Path) -> None:
    install_hooks(settings_path=settings_path, script_path=script_path)
    assert script_path.exists()
    assert script_path.read_text() == HOOK_SCRIPT
    # Must be executable.
    mode = script_path.stat().st_mode & 0o777
    assert mode & 0o111  # at least one execute bit set


def test_install_preserves_unrelated_keys(settings_path: Path, script_path: Path) -> None:
    """Existing top-level keys, model config, etc. survive the merge."""
    settings_path.write_text(
        json.dumps(
            {
                "model": "claude-opus-4-7",
                "permissions": {"allow": ["bash:ls"]},
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "",
                            "hooks": [
                                {"type": "command", "command": "/usr/local/bin/user-hook.sh"}
                            ],
                        }
                    ],
                },
            }
        )
    )

    install_hooks(settings_path=settings_path, script_path=script_path)

    data = json.loads(settings_path.read_text())
    assert data["model"] == "claude-opus-4-7"
    assert data["permissions"] == {"allow": ["bash:ls"]}
    # Existing user hook on SessionStart is preserved alongside ours.
    sess_start = data["hooks"]["SessionStart"]
    assert len(sess_start) == 2
    cmds = [entry["hooks"][0]["command"] for entry in sess_start]
    assert "/usr/local/bin/user-hook.sh" in cmds
    assert f"{script_path} SessionStart" in cmds


# ────────────────────── idempotency ──────────────────────


def test_install_is_idempotent(settings_path: Path, script_path: Path) -> None:
    """Re-running install on an already-installed config is a no-op."""
    first = install_hooks(settings_path=settings_path, script_path=script_path)
    second = install_hooks(settings_path=settings_path, script_path=script_path)
    assert first.changed is True
    assert second.changed is False
    assert second.backup_path is None


def test_install_does_not_duplicate_entries(settings_path: Path, script_path: Path) -> None:
    """After three install runs we still have exactly one entry per event."""
    for _ in range(3):
        install_hooks(settings_path=settings_path, script_path=script_path)
    data = json.loads(settings_path.read_text())
    for ev in HOOK_EVENTS:
        block = data["hooks"][ev]
        cmds = [
            h["command"]
            for entry in block
            for h in entry["hooks"]
            if h["command"].startswith(str(script_path))
        ]
        assert len(cmds) == 1, f"duplicated entries for {ev}: {cmds}"


# ────────────────────── backup ──────────────────────


def test_install_backs_up_existing_file(settings_path: Path, script_path: Path) -> None:
    """An existing settings.json is copied to ``*.bak.<timestamp>`` before write."""
    original = {"model": "claude-opus-4-7", "hooks": {}}
    settings_path.write_text(json.dumps(original))

    result = install_hooks(settings_path=settings_path, script_path=script_path)

    assert result.changed is True
    assert result.backup_path is not None
    assert result.backup_path.exists()
    backup_data = json.loads(result.backup_path.read_text())
    assert backup_data == original
    # Backup name follows the documented pattern.
    assert ".bak." in result.backup_path.name


def test_install_no_backup_when_file_missing(settings_path: Path, script_path: Path) -> None:
    """No backup is created when there's no pre-existing settings.json."""
    result = install_hooks(settings_path=settings_path, script_path=script_path)
    assert result.backup_path is None


# ────────────────────── dry-run ──────────────────────


def test_dry_run_does_not_write(settings_path: Path, script_path: Path) -> None:
    result = install_hooks(settings_path=settings_path, script_path=script_path, dry_run=True)
    assert result.changed is True
    assert not settings_path.exists()
    assert not script_path.exists()
    # Diff is non-empty when there's a change.
    assert "before" in result.diff
    assert "after" in result.diff


def test_dry_run_no_change_no_diff(settings_path: Path, script_path: Path) -> None:
    install_hooks(settings_path=settings_path, script_path=script_path)  # baseline
    result = install_hooks(settings_path=settings_path, script_path=script_path, dry_run=True)
    assert result.changed is False
    assert result.diff == ""


# ────────────────────── uninstall ──────────────────────


def test_uninstall_removes_csm_entries(settings_path: Path, script_path: Path) -> None:
    install_hooks(settings_path=settings_path, script_path=script_path)
    install_hooks(settings_path=settings_path, script_path=script_path, uninstall=True)

    data = json.loads(settings_path.read_text())
    # Either the hooks block is gone or has no csm-prefixed commands.
    hooks = data.get("hooks", {})
    for block in hooks.values():
        for entry in block:
            for h in entry.get("hooks", []):
                assert not h["command"].startswith(str(script_path))


def test_uninstall_preserves_unrelated_user_hooks(settings_path: Path, script_path: Path) -> None:
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "",
                            "hooks": [
                                {"type": "command", "command": "/usr/local/bin/user-hook.sh"}
                            ],
                        }
                    ]
                }
            }
        )
    )
    install_hooks(settings_path=settings_path, script_path=script_path)
    install_hooks(settings_path=settings_path, script_path=script_path, uninstall=True)

    data = json.loads(settings_path.read_text())
    sess_start = data["hooks"]["SessionStart"]
    assert len(sess_start) == 1
    assert sess_start[0]["hooks"][0]["command"] == "/usr/local/bin/user-hook.sh"


def test_uninstall_idempotent(settings_path: Path, script_path: Path) -> None:
    install_hooks(settings_path=settings_path, script_path=script_path)
    first = install_hooks(settings_path=settings_path, script_path=script_path, uninstall=True)
    second = install_hooks(settings_path=settings_path, script_path=script_path, uninstall=True)
    assert first.changed is True
    assert second.changed is False


# ────────────────────── hook script content ──────────────────────


def test_hook_script_is_shell_compatible() -> None:
    """The bundled script must declare a shebang and exit 0 unconditionally."""
    assert HOOK_SCRIPT.startswith("#!/bin/sh")
    assert "exit 0" in HOOK_SCRIPT
    # Don't `set -e` — we want failures to be silent so claude isn't blocked.
    assert "\nset -e" not in HOOK_SCRIPT
    # POSTs to the local collector.
    assert "http://127.0.0.1:8765/hook/" in HOOK_SCRIPT


# ────────────────────── invalid input ──────────────────────


def test_invalid_json_in_settings_rejected(settings_path: Path, script_path: Path) -> None:
    settings_path.write_text("not valid json {{{")
    with pytest.raises(Exception, match=r"not valid JSON|valid JSON"):
        install_hooks(settings_path=settings_path, script_path=script_path)


def test_corrupt_settings_still_gets_backed_up(
    settings_path: Path, script_path: Path
) -> None:
    """Even when settings.json is broken JSON (the case where backup
    matters MOST), the .bak.<timestamp> file must exist after the failed
    install attempt so the user can recover."""
    settings_path.write_text("not valid json {{{")
    pre_files = {p.name for p in settings_path.parent.glob("*.bak.*")}

    with pytest.raises(Exception, match=r"not valid JSON|valid JSON"):
        install_hooks(settings_path=settings_path, script_path=script_path)

    post_files = {p.name for p in settings_path.parent.glob("*.bak.*")}
    new_backups = post_files - pre_files
    assert len(new_backups) == 1, f"expected 1 new backup, got {new_backups}"
    # The backup must contain the original (corrupt) content verbatim.
    backup_name = next(iter(new_backups))
    assert (settings_path.parent / backup_name).read_text() == "not valid json {{{"


def test_non_object_settings_rejected(settings_path: Path, script_path: Path) -> None:
    settings_path.write_text("[1, 2, 3]")
    with pytest.raises(Exception, match="JSON object"):
        install_hooks(settings_path=settings_path, script_path=script_path)


# ────────────────────── Typer wiring ──────────────────────


def test_cli_hooks_dry_run(
    settings_path: Path, script_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``csm hooks --dry-run`` prints the diff without writing."""
    monkeypatch.setenv("HOME", str(script_path.parent.parent))
    runner = CliRunner()
    result = runner.invoke(cli_app, ["hooks", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.stdout or "No changes" in result.stdout
    # Either way, the file is not written.
    if "Dry run" in result.stdout:
        assert not settings_path.exists()


def test_cli_install_hooks_writes_file(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end: ``csm install-hooks`` actually mutates the settings file."""
    # Force the hook-script destination into tmp_path too so we don't write
    # to the user's real ~/.csm/.
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli_app, ["install-hooks"])
    assert result.exit_code == 0, result.stdout
    assert settings_path.exists()
    data = json.loads(settings_path.read_text())
    assert "SessionStart" in data["hooks"]
