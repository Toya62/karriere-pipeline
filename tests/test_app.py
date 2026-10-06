"""Tests for the strangler SPA static serving in :mod:`src.dashboard.app`.

Covers the ``/`` and ``/index.html`` SPA shell, the ``/app/{asset}`` build mount,
the ``/style.css`` shell-chrome route, and containment (traversal, missing,
symlink-escape, non-existent build directory).
"""

import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app


@pytest.fixture
def spa_client(tmp_path, monkeypatch):
    app_dir = tmp_path / "dashboard" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (app_dir / "assets").mkdir()
    (app_dir / "assets" / "index-abc123.js").write_text("console.log('spa');", encoding="utf-8")
    (app_dir / "assets" / "index-abc123.css").write_text(".x{}", encoding="utf-8")
    (tmp_path / "dashboard" / "style.css").write_text("body{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(), raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def test_root_and_index_serve_spa_html(spa_client):
    for path in ("/", "/index.html"):
        response = spa_client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.text == "<html>spa</html>"
        assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_app_mount_serves_hashed_assets_with_content_type(spa_client):
    response = spa_client.get("/app/assets/index-abc123.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.text == "console.log('spa');"

    css = spa_client.get("/app/assets/index-abc123.css")
    assert css.status_code == 200
    assert "css" in css.headers["content-type"]


def test_app_mount_rejects_traversal_and_missing_assets(spa_client):
    assert spa_client.get("/app/assets/index-missing.js").status_code == 404
    # Encoded traversal must be rejected by containment, never leak repo files.
    assert spa_client.get("/app/%2e%2e/.env").status_code == 404
    assert spa_client.get("/app/%2e%2e/style.css").status_code == 404


def test_app_mount_rejects_external_symlinked_assets(spa_client, tmp_path):
    outside = tmp_path / "secret.js"
    outside.write_text("evil", encoding="utf-8")
    link = tmp_path / "dashboard" / "app" / "evil.js"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable")

    assert spa_client.get("/app/evil.js").status_code == 404


def test_style_css_shell_route(spa_client):
    response = spa_client.get("/style.css")
    assert response.status_code == 200
    assert "css" in response.headers["content-type"]
    assert response.text == "body{}"


def test_no_build_directory_yields_clean_404(tmp_path, monkeypatch):
    (tmp_path / "dashboard").mkdir()
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(), raise_server_exceptions=False)
    try:
        assert client.get("/").status_code == 404
        assert client.get("/app/assets/anything.js").status_code == 404
    finally:
        client.close()
