# tests/test_log_sanitization.py
"""Bug #10: log viewer must not leak server paths or the ADMIN_EMAIL startup
warning to the browser. The log endpoints return a redacted tail; the log
file on disk is untouched (full tracebacks stay server-side)."""
import os

os.environ["DATABASE_URL"] = ""

import shutil
import uuid

import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.dashboard.routers.scraper import _sanitize_log_text
from src.db.database import create_user, setup_db

client = TestClient(app)

RAW_LOG = """2026-11-23 19:00:00,123 - src.db.database - WARNING - ADMIN_EMAIL is not set; admin-user seeding is disabled until it is configured.
2026-11-23 19:00:01,456 - scraper - INFO - Scraped 12 jobs from indeed
Traceback (most recent call last):
  File "/opt/karriere-pipeline/src/scrapers/linkedin.py", line 120, in scrape
    raise RuntimeError("portal down")
RuntimeError: portal down
2026-11-23 19:00:02,789 - scraper - INFO - Saved job https://www.linkedin.com/jobs/view/12345
2026-11-23 19:00:03,000 - scraper - INFO - open('/home/deploy/data/karriere.db') ok
"""


def test_sanitize_redacts_server_paths_to_basenames():
    out = _sanitize_log_text(RAW_LOG)
    assert "/opt/karriere-pipeline" not in out
    assert "/home/deploy" not in out
    # Traceback stays debuggable: file + line survive, directory does not.
    assert 'File "linkedin.py", line 120, in scrape' in out
    assert "Traceback (most recent call last):" in out
    assert "RuntimeError: portal down" in out
    assert "open('karriere.db') ok" in out


def test_sanitize_drops_admin_email_startup_warning():
    out = _sanitize_log_text(RAW_LOG)
    assert "ADMIN_EMAIL is not set" not in out
    assert "Scraped 12 jobs from indeed" in out


def test_sanitize_preserves_job_urls():
    out = _sanitize_log_text(RAW_LOG)
    assert "https://www.linkedin.com/jobs/view/12345" in out


def test_sanitize_leaves_clean_logs_untouched():
    clean = "2026-11-23 19:00:00 INFO ok\nsecond line\n"
    assert _sanitize_log_text(clean) == clean


@pytest.fixture(scope="module")
def seeded_user():
    setup_db()
    uid = uuid.uuid4().hex[:8]
    user = create_user(
        email=f"log_test_{uid}@example.com",
        hashed_password="x" * 10,
        full_name="Log Test User",
        role="candidate",
        tier="pro",
        is_verified=True,
    )
    token = create_access_token(data={"sub": f"user_{user['id']}", "user_id": user["id"]})
    return {"user_id": user["id"], "token": token}


def _write_log(user_id, name, content):
    log_dir = os.path.join("data", "logs", str(user_id))
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_log_endpoints_return_redacted_tail(seeded_user):
    """Bug #10: both log endpoints redact paths + the ADMIN_EMAIL line, and
    the file on disk still holds the original text."""
    headers = {"Authorization": f"Bearer {seeded_user['token']}"}
    user_id = seeded_user["user_id"]
    paths = []
    try:
        paths.append(_write_log(user_id, "scraper.log", RAW_LOG))
        paths.append(_write_log(user_id, "matcher.log", RAW_LOG))
        for endpoint in ("/api/scraper-logs", "/api/matcher-logs"):
            r = client.get(endpoint, headers=headers)
            assert r.status_code == 200
            logs = r.json()["logs"]
            assert "/opt/karriere-pipeline" not in logs
            assert "ADMIN_EMAIL is not set" not in logs
            assert 'File "linkedin.py", line 120, in scrape' in logs
            assert "https://www.linkedin.com/jobs/view/12345" in logs
        # On-disk logs are untouched: full paths + warning still there.
        for path in paths:
            with open(path, encoding="utf-8") as f:
                on_disk = f.read()
            assert "/opt/karriere-pipeline/src/scrapers/linkedin.py" in on_disk
            assert "ADMIN_EMAIL is not set" in on_disk
    finally:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            shutil.rmtree(os.path.join("data", "logs", str(user_id)))
        except OSError:
            pass
