"""Security and behavior tests for the FastAPI dashboard API.

The dashboard is now served by FastAPI/uvicorn; these tests drive it through
``fastapi.testclient.TestClient`` while preserving the original coverage:
explicit asset allowlisting, PDF containment, loopback-only CORS, bounded
caches, scraper subprocess control, and SQLite-backed dataset views.
"""

import json

import pytest
from fastapi.testclient import TestClient

from src.dashboard import state
from src.dashboard.app import create_app
from src.dashboard.server import DEFAULT_HOST


def test_dashboard_server_exports():
    from src.dashboard import server
    assert hasattr(server, 'run')
    assert hasattr(server, 'app')
    assert callable(server.create_app)


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
    from src.dashboard import server
    from src.dashboard.app import _dashboard_build_dir

    prefix = tmp_path / "prefix"
    asset_dir = prefix / "dashboard"
    asset_dir.mkdir(parents=True)
    (asset_dir / "style.css").write_text("body {}", encoding="utf-8")
    (asset_dir / "app").mkdir()
    (asset_dir / "app" / "index.html").write_text("installed dashboard", encoding="utf-8")
    working_dir = tmp_path / "outside-checkout"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(server.sys, "prefix", str(prefix))

    assert server._dashboard_asset_path("style.css") == str(asset_dir / "style.css")
    assert _dashboard_build_dir() == (asset_dir / "app").resolve()


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "app").mkdir()
    (tmp_path / "dashboard" / "app" / "index.html").write_text("dashboard spa", encoding="utf-8")
    (tmp_path / "dashboard" / "app" / "assets").mkdir()
    (tmp_path / "dashboard" / "app" / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "dashboard" / "style.css").write_text("body {}", encoding="utf-8")
    (tmp_path / "applications" / "2026-10-02").mkdir(parents=True)
    (tmp_path / "applications" / "2026-10-02" / "cv.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "karriere.db").write_bytes(b"private database")
    (tmp_path / ".env").write_text("TOKEN=private", encoding="utf-8")

    client = TestClient(create_app(), raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def test_dashboard_serves_only_explicit_assets_and_application_pdfs(dashboard):
    assert dashboard.get("/").status_code == 200
    assert dashboard.get("/index.html").status_code == 200
    assert dashboard.get("/style.css").status_code == 200
    asset = dashboard.get("/app/assets/index-abc123.js")
    assert asset.status_code == 200
    assert "javascript" in asset.headers["content-type"]
    response = dashboard.get("/applications/2026-10-02/cv.pdf")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4"

    for path in (
        "/.env",
        "/data/karriere.db",
        "/app/%2e%2e/.env",
        "/app/%2e%2e/style.css",
        "/../.env",
        "/%2e%2e/.env",
        "/applications/2026-10-02/cv.tex",
    ):
        assert dashboard.get(path).status_code == 404


def test_dashboard_does_not_serve_unlisted_dashboard_files(dashboard, tmp_path):
    (tmp_path / "dashboard" / "secret.txt").write_text("private", encoding="utf-8")
    assert dashboard.get("/secret.txt").status_code == 404


def test_dashboard_does_not_serve_symlinked_external_pdfs(dashboard, tmp_path):
    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"private")
    link = tmp_path / "applications" / "2026-10-02" / "external.pdf"
    try:
        link.symlink_to(outside_pdf)
    except OSError:
        pytest.skip("Symlinks are unavailable")

    assert dashboard.get("/applications/2026-10-02/external.pdf").status_code == 404


def test_dashboard_rejects_cross_origin_github_pages_preflight(dashboard):
    response = dashboard.options("/api/run-scraper", headers={"Origin": "https://attacker.github.io"})
    assert response.status_code == 403


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

    assert _is_origin_allowed("https://evil-site.com") is False
    assert _is_origin_allowed("http://attacker.org:8000") is False
    assert _is_origin_allowed("https://fakegithub.io") is False


def test_bounded_desc_cache():
    """Verify that description cache does not grow unboundedly."""
    from src.dashboard.server import _DESC_CACHE, _set_desc_cache

    _DESC_CACHE.clear()
    for i in range(1050):
        _set_desc_cache(f"url_{i}", f"description content {i}")

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


def test_dashboard_request_body_validation(dashboard):
    """Oversized, malformed, and missing bodies are rejected with JSON errors."""
    # Missing body -> FastAPI validation mapped to a 400 JSON error.
    response = dashboard.post("/api/applications")
    assert response.status_code == 400
    assert "error" in response.json()

    # Oversized payload -> 413 before routing.
    oversized = dashboard.post(
        "/api/applications",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "20000000"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"].startswith("Payload exceeds limit")

    # Malformed JSON -> 400.
    bad_json = dashboard.post(
        "/api/applications",
        content=b"not-a-json{",
        headers={"Content-Type": "application/json"},
    )
    assert bad_json.status_code == 400
    assert "error" in bad_json.json()


def test_dashboard_trigger_scraper_locally(dashboard):
    """Verify triggering the scraper runs locally via subprocess."""
    from unittest.mock import MagicMock, patch

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    state.SCRAPER_PROCESS = None
    try:
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            response = dashboard.post("/api/run-scraper", json={"portal": "linkedin", "days": 3})
            assert response.status_code == 200
            data = response.json()
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
    finally:
        state.SCRAPER_PROCESS = None


def test_dashboard_trigger_scraper_rejects_concurrent_run(dashboard):
    """Verify starting scraper when one is already running returns 400."""
    from unittest.mock import MagicMock

    running_proc = MagicMock()
    running_proc.poll.return_value = None
    state.SCRAPER_PROCESS = running_proc

    try:
        response = dashboard.post("/api/trigger-github-scraper", json={"portal": "all", "days": 1})
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "already running" in data["error"]
    finally:
        state.SCRAPER_PROCESS = None


def test_dashboard_scraper_logs_endpoint(dashboard, tmp_path):
    """Verify /api/scraper-logs returns log content and handles missing file gracefully."""
    log_file = tmp_path / "data" / "scraper_run.log"
    if log_file.exists():
        log_file.unlink()

    response = dashboard.get("/api/scraper-logs")
    assert response.status_code == 200
    assert response.json()["success"] is True

    log_file.write_text("Line 1\nLine 2\nScraping complete\n", encoding="utf-8")
    response = dashboard.get("/api/scraper-logs")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Scraping complete" in data["logs"]


def test_dashboard_pure_sqlite_views_and_dismissal(dashboard, tmp_path):
    import sqlite3

    from src.db.database import setup_db

    data_dir = tmp_path / "data"
    db_file = data_dir / "karriere.db"
    if db_file.exists():
        db_file.unlink()
    conn = setup_db(db_file)
    conn.execute(
        "INSERT INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)",
        ("TestCorp", "Python Dev", "https://example.com/job1", "Desc"),
    )
    conn.execute(
        "INSERT INTO evaluations (job_id, status, score, chance) VALUES (1, 'APPROVED', 85, 'HIGH')",
    )
    conn.commit()
    conn.close()

    datasets = dashboard.get("/api/datasets")
    assert datasets.status_code == 200
    assert "ai_approved" in datasets.json()
    assert "all_combined" in datasets.json()

    approved = dashboard.get("/api/approved-index")
    assert approved.status_code == 200
    payload = approved.json()
    assert len(payload) == 1
    assert payload[0]["company"] == "TestCorp"

    from src.dashboard.server import _add_to_dismissed, _load_dismissed_df
    _add_to_dismissed(job_url="https://example.com/job1")
    dismissed_df = _load_dismissed_df()
    assert len(dismissed_df) == 1
    assert dismissed_df.iloc[0]["job_url"] == "https://example.com/job1"

    conn = sqlite3.connect(data_dir / "karriere.db")
    status = conn.execute("SELECT status FROM evaluations WHERE job_id = 1").fetchone()[0]
    conn.close()
    assert status == "USER_DISMISSED"


def test_cors_headers_added_to_api_responses(dashboard):
    response = dashboard.get("/api/datasets", headers={"Origin": "http://localhost:8000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"


def test_generation_status_requires_task_key(dashboard):
    response = dashboard.get("/api/generate-application/status")
    assert response.status_code == 400
    assert response.json() == {"error": "Missing task_key parameter"}


def test_error_responses_are_json(dashboard):
    response = dashboard.get("/definitely-not-a-route")
    assert response.status_code == 404
    assert "error" in response.json()
    assert json.dumps(response.json())  # serializable
