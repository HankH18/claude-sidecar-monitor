"""Smoke tests — version, healthz, CLI app loads."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import csm
from csm import server
from csm.cli import app as cli_app
from csm.db import connect
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


# ────────── dashboard shell + csm-token templating ──────────


@pytest.fixture
def app_with_static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """create_app() wired to a fake static bundle and a seeded DB.

    Avoids the real lifespan so we don't touch the user's ~/Library/...
    storage; tests need only the routes + app.state.db.
    """
    static_dir = tmp_path / "_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><head>"
        '<meta name="csm-token" content="__CSM_TOKEN__">'
        "</head><body>app</body></html>",
        encoding="utf-8",
    )
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "app.js").write_text("console.log('hi')")

    monkeypatch.setattr(server, "_resolve_static_dir", lambda: static_dir)

    app = create_app()
    # No lifespan in this test path — manually attach a DB so the
    # / and /{full_path:path} routes can read api_secret from settings.
    app.state.db = connect(db_path=tmp_path / "store.db")
    app.state.db.execute(
        "UPDATE settings SET value = ? WHERE key = 'api_secret'", ("test-secret-xyz",)
    )
    try:
        yield app
    finally:
        app.state.db.close()


def test_index_substitutes_csm_token(app_with_static) -> None:
    client = TestClient(app_with_static)
    r = client.get("/")
    assert r.status_code == 200
    assert "test-secret-xyz" in r.text
    assert "__CSM_TOKEN__" not in r.text
    assert r.headers["cache-control"] == "no-store"


def test_spa_fallback_serves_index_for_unknown_route(app_with_static) -> None:
    client = TestClient(app_with_static)
    r = client.get("/permissions/42")
    assert r.status_code == 200
    assert "test-secret-xyz" in r.text


def test_asset_served_directly(app_with_static) -> None:
    client = TestClient(app_with_static)
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_api_404_not_shadowed_by_spa(app_with_static) -> None:
    client = TestClient(app_with_static)
    # /api/bogus is not a registered API route — must 404, not return HTML.
    r = client.get("/api/bogus")
    assert r.status_code == 404
    assert "<html" not in r.text.lower()


def test_directory_traversal_blocked(app_with_static, tmp_path: Path) -> None:
    # Drop a "secret" outside the static dir; the catch-all must not
    # serve it via path traversal.
    secret = tmp_path / "secret.txt"
    secret.write_text("DO NOT LEAK")
    client = TestClient(app_with_static)
    # Encoded traversal — httpx normalises path separators server-side,
    # so probe a few shapes. None should leak the secret.
    for path in ("/..%2fsecret.txt", "/static/../secret.txt"):
        r = client.get(path)
        assert "DO NOT LEAK" not in r.text


def test_index_empty_token_when_secret_unset(tmp_path: Path, monkeypatch) -> None:
    static_dir = tmp_path / "_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        '<meta name="csm-token" content="__CSM_TOKEN__">',
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "_resolve_static_dir", lambda: static_dir)
    app = create_app()
    app.state.db = connect(db_path=tmp_path / "store.db")  # api_secret seeded ''
    try:
        client = TestClient(app)
        r = client.get("/")
        # Empty substitution still strips the placeholder.
        assert r.status_code == 200
        assert "__CSM_TOKEN__" not in r.text
        assert 'content=""' in r.text
    finally:
        app.state.db.close()
