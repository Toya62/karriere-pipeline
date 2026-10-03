import json
import socketserver
import threading
import urllib.error
import urllib.request

import pytest

from src.dashboard.server import DEFAULT_HOST, DashboardHandler


def test_dashboard_server_exports():
    import src.dashboard.server as server
    assert hasattr(server, 'run')
    assert hasattr(server, 'DashboardHandler')

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


def test_cors_origin_validator():
    """Verify CORS validation allows local development but rejects remote origins."""
    from src.dashboard.server import _cors_origin_header, _is_origin_allowed

    assert _is_origin_allowed("") is True
    assert _is_origin_allowed("http://localhost:8000") is True
    assert _is_origin_allowed("http://127.0.0.1:8000") is True
    assert _is_origin_allowed("https://localhost:3000") is True
    assert _cors_origin_header("https://localhost:3000") == "https://localhost:3000"
    assert _cors_origin_header("https://localhost:3000\r\nX-Evil: injected") is None
    assert _is_origin_allowed("https://YOUR_GITHUB_USERNAME.github.io") is False

    # Malicious / external origins must be rejected
    assert _is_origin_allowed("https://evil-site.com") is False
    assert _is_origin_allowed("http://attacker.org:8000") is False
    assert _is_origin_allowed("https://fakegithub.io") is False


def test_bounded_desc_cache():
    """Verify that description cache does not grow unboundedly."""
    from src.dashboard.server import _DESC_CACHE, _set_desc_cache

    _DESC_CACHE.clear()
    for i in range(1050):
        _set_desc_cache(f"url_{i}", f"description content {i}")

    # Must be bounded (under 1000 after eviction of 200)
    assert len(_DESC_CACHE) <= 1000
    assert "url_1049" in _DESC_CACHE


def test_bounded_app_gen_status():
    """Verify that application generation status map does not grow unboundedly."""
    from src.dashboard.server import _APP_GEN_STATUS, _set_gen_status

    _APP_GEN_STATUS.clear()
    for i in range(250):
        _set_gen_status(f"task_{i}", {"status": "complete", "id": i})

    assert len(_APP_GEN_STATUS) <= 200
    assert "task_249" in _APP_GEN_STATUS


def test_read_json_body_error_handling():
    """Verify DashboardHandler._read_json_body handles missing headers, invalid JSON, and oversized payloads."""
    import io
    import json
    from unittest.mock import patch

    handler = DashboardHandler.__new__(DashboardHandler)

    # 1. Missing Content-Length header
    handler.headers = {}
    handler.wfile = io.BytesIO()
    with patch("src.dashboard.server._send_json") as mock_send_json:
        res = handler._read_json_body()
        assert res is None
        mock_send_json.assert_called_with(handler, 400, {"error": "Missing Content-Length header"})

    # 2. Oversized payload
    handler.headers = {"Content-Length": "20000000"}  # 20MB
    with patch("src.dashboard.server._send_json") as mock_send_json:
        res = handler._read_json_body(max_bytes=10 * 1024 * 1024)
        assert res is None
        assert mock_send_json.call_args[0][1] == 413

    # 3. Invalid JSON
    bad_json = b"not-a-json{"
    handler.headers = {"Content-Length": str(len(bad_json))}
    handler.rfile = io.BytesIO(bad_json)
    with patch("src.dashboard.server._send_json") as mock_send_json:
        res = handler._read_json_body()
        assert res is None
        assert mock_send_json.call_args[0][1] == 400

    # 4. Valid JSON
    valid_data = {"action": "test", "items": [1, 2, 3]}
    valid_json = json.dumps(valid_data).encode("utf-8")
    handler.headers = {"Content-Length": str(len(valid_json))}
    handler.rfile = io.BytesIO(valid_json)
    res = handler._read_json_body()
    assert res == valid_data


def test_dashboard_trigger_scraper_locally(dashboard):
    """Verify triggering scraper runs locally via subprocess without calling GitHub Actions."""
    import json
    from unittest.mock import MagicMock, patch
    import src.dashboard.server as server

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        server._SCRAPER_PROCESS = None
        req = urllib.request.Request(
            f"{dashboard}/api/run-scraper",
            data=b'{"portal": "linkedin", "days": 3}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["success"] is True
            assert data["mode"] == "local"
            assert "Local scraper started" in data["message"]

        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "main.py" in cmd
        assert "scrape" in cmd
        assert "--portal" in cmd
        assert "linkedin" in cmd
        assert "--days" in cmd
        assert "3" in cmd
        server._SCRAPER_PROCESS = None


def test_dashboard_trigger_scraper_rejects_concurrent_run(dashboard):
    """Verify starting scraper when one is already running returns 400."""
    from unittest.mock import MagicMock
    import src.dashboard.server as server

    running_proc = MagicMock()
    running_proc.poll.return_value = None
    server._SCRAPER_PROCESS = running_proc

    try:
        req = urllib.request.Request(
            f"{dashboard}/api/trigger-github-scraper",
            data=b'{"portal": "all", "days": 1}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                pytest.fail("Expected HTTP 400 error")
        except urllib.error.HTTPError as err:
            assert err.code == 400
            data = json.loads(err.read().decode())
            assert data["success"] is False
            assert "already running" in data["error"]
    finally:
        server._SCRAPER_PROCESS = None


def test_dashboard_scraper_logs_endpoint(dashboard, tmp_path):
    """Verify /api/scraper-logs returns log content and handles missing file gracefully."""
    # 1. Missing log file returns message
    log_file = tmp_path / "data" / "scraper_run.log"
    if log_file.exists():
        log_file.unlink()

    code, resp_bytes = _get(f"{dashboard}/api/scraper-logs")
    assert code == 200
    data = json.loads(resp_bytes.decode())
    assert data["success"] is True

    # 2. Existing log file returns contents
    log_file.write_text("Line 1\nLine 2\nScraping complete\n", encoding="utf-8")
    code, resp_bytes = _get(f"{dashboard}/api/scraper-logs")
    assert code == 200
    data = json.loads(resp_bytes.decode())
    assert data["success"] is True
    assert "Scraping complete" in data["logs"]



