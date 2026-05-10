"""Tests for ``csm install-launchd`` plist rendering + sandbox-safety.

The harness blocks ``launchctl``; these tests verify the code degrades
gracefully rather than crashing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from csm.cli._launchd_template import PLIST_TEMPLATE
from csm.cli.launchd import (
    LAUNCHD_LABEL,
    install_launchd,
    render_plist,
    uninstall_launchd,
)


def test_render_plist_substitutes_all_placeholders(tmp_path: Path) -> None:
    rendered = render_plist(
        csm_bin="/Users/test/.local/bin/csm",
        user="testuser",
        home=tmp_path,
    )
    assert "__CSM_BIN__" not in rendered
    assert "__USER__" not in rendered
    assert "__HOME__" not in rendered
    assert "/Users/test/.local/bin/csm" in rendered
    assert "<string>testuser</string>" in rendered
    assert str(tmp_path) in rendered


def test_install_launchd_writes_plist_no_bootstrap(tmp_path: Path) -> None:
    plist = tmp_path / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    result = install_launchd(
        plist_path=plist,
        csm_bin="/Users/test/.local/bin/csm",
        user="testuser",
        home=tmp_path,
        attempt_bootstrap=False,
    )
    assert result.plist_path == plist
    assert plist.exists()
    assert result.bootstrap_attempted is False
    contents = plist.read_text()
    assert "/Users/test/.local/bin/csm" in contents
    # Manual command format is documented and includes gui/<UID>.
    assert "launchctl bootstrap gui/" in result.manual_command
    assert str(plist) in result.manual_command


def test_install_launchd_handles_missing_launchctl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If launchctl isn't on PATH, the function still writes the plist."""

    def fake_run(*_: Any, **__: Any) -> None:
        raise FileNotFoundError("launchctl not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    plist = tmp_path / f"{LAUNCHD_LABEL}.plist"
    result = install_launchd(
        plist_path=plist,
        csm_bin="/Users/test/.local/bin/csm",
        user="testuser",
        home=tmp_path,
        attempt_bootstrap=True,
    )
    assert plist.exists()
    assert result.bootstrap_attempted is True
    assert result.bootstrap_ok is False
    assert "not found" in result.bootstrap_message


def test_install_launchd_handles_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A nonzero ``launchctl`` exit doesn't raise — it's reported."""

    class FakeResult:
        def __init__(self) -> None:
            self.returncode = 5
            self.stdout = ""
            self.stderr = "Service already loaded"

    def fake_run(*_: Any, **__: Any) -> FakeResult:
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    plist = tmp_path / f"{LAUNCHD_LABEL}.plist"
    result = install_launchd(
        plist_path=plist,
        csm_bin="/Users/test/.local/bin/csm",
        user="testuser",
        home=tmp_path,
    )
    assert result.bootstrap_ok is False
    assert "exit=5" in result.bootstrap_message
    assert plist.exists()  # plist was still written


def test_install_launchd_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResult:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = "loaded"
            self.stderr = ""

    def fake_run(*_: Any, **__: Any) -> FakeResult:
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    plist = tmp_path / f"{LAUNCHD_LABEL}.plist"
    result = install_launchd(
        plist_path=plist,
        csm_bin="/Users/test/.local/bin/csm",
        user="testuser",
        home=tmp_path,
    )
    assert result.bootstrap_ok is True


def test_uninstall_launchd_removes_plist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """uninstall_launchd unlinks the plist after best-effort bootout."""

    class FakeResult:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    def fake_run(*_: Any, **__: Any) -> FakeResult:
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    plist = tmp_path / f"{LAUNCHD_LABEL}.plist"
    plist.write_text("placeholder")
    removed, _ = uninstall_launchd(plist_path=plist)
    assert removed is True
    assert not plist.exists()


def test_uninstall_launchd_when_plist_absent(tmp_path: Path) -> None:
    plist = tmp_path / "missing.plist"
    removed, msg = uninstall_launchd(plist_path=plist)
    assert removed is True  # nothing to remove == success
    assert msg == "skipped"


def test_template_in_sync_with_repo_copy() -> None:
    """The bundled template must mirror ``scripts/launchd/...`` exactly.

    If a contributor edits one and not the other, the LaunchAgent install
    would silently drift. This test guards against that.
    """
    repo_root = Path(__file__).resolve().parents[4]
    on_disk = repo_root / "scripts" / "launchd" / "com.hank.claude-sidecar-monitor.plist.template"
    if not on_disk.exists():
        pytest.skip(f"repo template not found at {on_disk}")
    assert on_disk.read_text() == PLIST_TEMPLATE
