import socketserver
import threading
import urllib.error
import urllib.request

import pytest

from src.dashboard.server import DEFAULT_HOST, DashboardHandler


def test_dashboard_binds_to_loopback_by_default():
    assert DEFAULT_HOST == "127.0.0.1"

def test_dashboard_uses_configured_container_host(monkeypatch):
    import main

    calls = []
    monkeypatch.setenv("DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setattr(main, "run_server", lambda **kwargs: calls.append(kwargs))

    main.handle_dashboard(type("Args", (), {"port": 8123})())

    assert calls == [{"port": 8123, "host": "0.0.0.0"}]


def test_installed_dashboard_resolves_packaged_assets(tmp_path, monkeypatch):
    import src.dashboard.server as server

    asset_dir = tmp_path / "prefix" / "dashboard"
    asset_dir.mkdir(parents=True)
    (asset_dir / "index.html").write_text("installed dashboard", encoding="utf-8")
    working_dir = tmp_path / "outside-checkout"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(server.sys, "prefix", str(tmp_path / "prefix"))

    assert server._dashboard_asset_path("index.html") == str(asset_dir / "index.html")


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "index.html").write_text("dashboard", encoding="utf-8")
    (tmp_path / "dashboard" / "style.css").write_text("body {}", encoding="utf-8")
    (tmp_path / "applications" / "2026-10-02").mkdir(parents=True)
    (tmp_path / "applications" / "2026-10-02" / "cv.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "karriere.db").write_bytes(b"private database")
    (tmp_path / ".env").write_text("TOKEN=private", encoding="utf-8")

    server = socketserver.TCPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get(url):
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()

def _options(url, origin):
    request = urllib.request.Request(url, method="OPTIONS", headers={"Origin": origin})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_dashboard_serves_only_explicit_assets_and_application_pdfs(dashboard):
    assert _get(f"{dashboard}/")[0] == 200
    assert _get(f"{dashboard}/style.css")[0] == 200
    status, pdf = _get(f"{dashboard}/applications/2026-10-02/cv.pdf")
    assert status == 200
    assert pdf == b"%PDF-1.4"

    for path in ("/.env", "/data/karriere.db", "/../.env", "/%2e%2e/.env", "/applications/2026-10-02/cv.tex"):
        assert _get(f"{dashboard}{path}")[0] == 404


def test_dashboard_does_not_serve_unlisted_dashboard_files(dashboard, tmp_path):
    (tmp_path / "dashboard" / "secret.txt").write_text("private", encoding="utf-8")
    assert _get(f"{dashboard}/secret.txt")[0] == 404


def test_dashboard_does_not_serve_symlinked_external_pdfs(dashboard, tmp_path):
    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"private")
    link = tmp_path / "applications" / "2026-10-02" / "external.pdf"
    try:
        link.symlink_to(outside_pdf)
    except OSError:
        pytest.skip("Symlinks are unavailable")

    assert _get(f"{dashboard}/applications/2026-10-02/external.pdf")[0] == 404


def test_dashboard_rejects_cross_origin_github_pages_preflight(dashboard):
    assert _options(f"{dashboard}/api/run-scraper", "https://attacker.github.io") == 403
