import sys
import os
import ssl
import json
import io
import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ai.router import _get_ssl_context
import src.config as config
from src.scrapers.orchestrator import _compute_score
from src.db.file_io import _save_csv
from src.dashboard.server import (
    _is_origin_allowed,
    _set_desc_cache,
    _set_gen_status,
    _DESC_CACHE,
    _APP_GEN_STATUS,
    DashboardHandler,
)


def test_strict_tls_context():
    """Verify that TLS context enforces certificate validation and hostname check."""
    ctx = _get_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode != ssl.CERT_NONE, "TLS must not allow CERT_NONE"
    assert ctx.check_hostname is True, "TLS must check hostname"


def test_dynamic_scrape_window_config():
    """Verify that SCRAPE_WINDOW changes dynamically reflect in MAX_DAYS and WINDOW_TAG."""
    orig = os.environ.get("SCRAPE_WINDOW")
    try:
        os.environ["SCRAPE_WINDOW"] = "1d"
        assert config.MAX_DAYS == 1
        assert config.WINDOW_TAG == "1d"

        os.environ["SCRAPE_WINDOW"] = "7d"
        assert config.MAX_DAYS == 7
        assert config.WINDOW_TAG == "7d"

        os.environ["SCRAPE_WINDOW"] = "3"
        assert config.MAX_DAYS == 3
        assert config.WINDOW_TAG == "3d"
    finally:
        if orig is not None:
            os.environ["SCRAPE_WINDOW"] = orig
        else:
            os.environ.pop("SCRAPE_WINDOW", None)


def test_linkedin_orchestrator_uses_runtime_scrape_window(monkeypatch):
    import src.scrapers.orchestrator as orchestrator_module

    monkeypatch.setenv("SCRAPE_WINDOW", "1d")
    importlib.reload(orchestrator_module)

    observed_hours = []
    linkedin_module = ModuleType("src.scrapers.linkedin")
    linkedin_module.scrape_linkedin = lambda query, results_wanted, hours_old: (
        observed_hours.append(hours_old) or pd.DataFrame()
    )
    linkedin_module.hydrate_linkedin_jobs = lambda jobs, max_workers: jobs
    monkeypatch.setitem(sys.modules, "src.scrapers.linkedin", linkedin_module)
    monkeypatch.setattr(orchestrator_module, "BOOLEAN_QUERIES", ["test query"])
    monkeypatch.setattr(orchestrator_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(orchestrator_module, "finalise", lambda *args, **kwargs: None)
    monkeypatch.setenv("SCRAPE_WINDOW", "7d")

    orchestrator_module.run_scrape_linkedin()

    assert observed_hours == [174]


def test_scraper_wrappers_use_runtime_scrape_window(monkeypatch):
    from src.scrapers import indeed, linkedin

    monkeypatch.setenv("SCRAPE_WINDOW", "1d")
    importlib.reload(linkedin)
    importlib.reload(indeed)
    observed_hours = {}
    monkeypatch.setattr(
        linkedin,
        "scrape_jobs",
        lambda **kwargs: observed_hours.update(linkedin=kwargs["hours_old"]) or pd.DataFrame(),
    )
    monkeypatch.setattr(
        indeed,
        "scrape_jobs",
        lambda **kwargs: observed_hours.update(indeed=kwargs["hours_old"]) or pd.DataFrame(),
    )
    monkeypatch.setenv("SCRAPE_WINDOW", "7d")

    linkedin.scrape_linkedin("test query")
    indeed.scrape_indeed("test query")

    assert observed_hours == {"linkedin": 174, "indeed": 168}


def test_all_portals_banner_uses_runtime_scrape_window(monkeypatch, tmp_path, capsys):
    import main as main_module

    monkeypatch.setenv("SCRAPE_WINDOW", "1d")
    importlib.reload(main_module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main_module,
        "_run_portal_and_ai",
        lambda *args, **kwargs: {"scraped": 0, "approved": 0},
    )
    monkeypatch.setattr("src.db.file_io.rebuild_all_time_combined", lambda: None)

    main_module.handle_scrape(SimpleNamespace(days=7, portal="all", no_match=True))

    assert "Window : 7d" in capsys.readouterr().out


def test_workflow_has_no_stale_matcher_status_reference():
    workflow_path = Path(__file__).parents[1] / ".github/workflows/hourly_scraper.yml"
    if not workflow_path.exists():
        pytest.skip("hourly_scraper.yml removed in favor of local scraping")
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "steps.matcher.outcome" not in workflow
    assert "matcher_status" not in workflow


def test_compute_score_date_freshness():
    """Verify that invalid/missing dates return 0 rather than falsely scoring 25."""
    assert _compute_score(None) == 0
    assert _compute_score("") == 0
    assert _compute_score("invalid-date-xyz") == 0
    assert _compute_score("NaN") == 0
    assert _compute_score("NaT") == 0

    # Real fresh date (< 24h)
    from datetime import datetime, timezone
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    score = _compute_score(now_iso)
    assert score >= 40, f"Expected high score for fresh date, got {score}"


def test_atomic_csv_write(tmp_path):
    """Verify that _save_csv writes atomically and leaves no corrupted partial files."""
    test_csv = str(tmp_path / "test_data.csv")
    df = pd.DataFrame([{"title": "Dev", "company": "TestCorp", "job_url": "https://example.com/job1"}])

    _save_csv(df, test_csv)
    assert os.path.exists(test_csv)

    loaded = pd.read_csv(test_csv)
    assert len(loaded) == 1
    assert loaded.iloc[0]["company"] == "TestCorp"

    # Verify no dangling temp files left behind
    temp_files = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert len(temp_files) == 0


def test_cors_origin_validator():
    """Verify CORS validation allows local development but rejects remote origins."""
    from src.dashboard.server import _cors_origin_header

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
    _DESC_CACHE.clear()
    for i in range(1050):
        _set_desc_cache(f"url_{i}", f"description content {i}")

    # Must be bounded (under 1000 after eviction of 200)
    assert len(_DESC_CACHE) <= 1000
    assert f"url_1049" in _DESC_CACHE


def test_bounded_app_gen_status():
    """Verify that application generation status map does not grow unboundedly."""
    _APP_GEN_STATUS.clear()
    for i in range(250):
        _set_gen_status(f"task_{i}", {"status": "complete", "id": i})

    assert len(_APP_GEN_STATUS) <= 200
    assert f"task_249" in _APP_GEN_STATUS


def test_read_json_body_error_handling():
    """Verify DashboardHandler._read_json_body handles missing headers, invalid JSON, and oversized payloads."""
    # Create a mock DashboardHandler instance
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
