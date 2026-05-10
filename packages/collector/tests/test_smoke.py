"""Smoke tests — version, healthz, CLI app loads."""

from __future__ import annotations

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import csm
from csm.cli import app as cli_app
from csm.server import create_app


def test_version() -> None:
    assert csm.__version__ == "0.1.0"


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "version": csm.__version__}


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["version"])
    assert result.exit_code == 0
    assert "csm v0.1.0" in result.stdout
