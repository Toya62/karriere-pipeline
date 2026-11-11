"""Tests for scraper log isolation and multi-tenant scraper runs."""

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.core.security import create_access_token
from src.dashboard.app import create_app
from src.db.database import (
    create_scraper_run,
    get_user_scraper_runs,
    setup_db,
    update_scraper_run,
)


@pytest.fixture(autouse=True)
def seed_test_users():
    setup_db()
    from src.db.database import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        for uid in (77, 99, 100):
            cur.execute(
                "INSERT INTO users (id, email, full_name, role, tier, is_verified) VALUES (?, ?, ?, ?, ?, 1) ON CONFLICT (id) DO UPDATE SET is_verified=1",
                (uid, f"user_{uid}@example.com", f"User {uid}", "user", "pro")
            )
        conn.commit()
    finally:
        conn.close()
    yield
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM scraper_runs WHERE user_id IN (77, 99, 100)")
        cur.execute("DELETE FROM users WHERE id IN (77, 99, 100)")
        conn.commit()
    finally:
        conn.close()
    import shutil
    for uid in (77, 99, 100):
        log_dir = os.path.join("data", "logs", str(uid))
        if os.path.exists(log_dir):
            shutil.rmtree(log_dir, ignore_errors=True)


@pytest.fixture
def client():
    setup_db()
    app = create_app()
    return TestClient(app)


def test_guest_cannot_view_server_stdout_logs(client):
    """Unauthenticated guest querying /api/scraper/logs gets empty log and guest=True."""
    resp = client.get("/api/scraper/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["guest"] is True
    assert data["logs"] == ""
    assert data["total_lines"] == 0

    matcher_resp = client.get("/api/matcher/logs")
    assert matcher_resp.status_code == 200
    m_data = matcher_resp.json()
    assert m_data["guest"] is True
    assert m_data["logs"] == ""


def test_authenticated_user_isolated_logs(client):
    """User receives only their own logs from data/logs/{user_id}/."""
    user_id = 99
    token = create_access_token({"user_id": user_id, "email": "user99@example.com", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}

    user_log_dir = os.path.join("data", "logs", str(user_id))
    os.makedirs(user_log_dir, exist_ok=True)
    user_log_file = os.path.join(user_log_dir, "scraper.log")
    with open(user_log_file, "w", encoding="utf-8") as f:
        f.write("User 99 Scrape started for Civil Engineering\nFound 5 jobs\n")

    resp = client.get("/api/scraper/logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("guest") is False or "guest" not in data
    assert "User 99 Scrape started" in data["logs"]

    # Another user cannot see user 99's log
    other_token = create_access_token({"user_id": 100, "email": "user100@example.com", "role": "user"})
    other_headers = {"Authorization": f"Bearer {other_token}"}
    other_resp = client.get("/api/scraper/logs", headers=other_headers)
    assert other_resp.status_code == 200
    assert "User 99 Scrape started" not in other_resp.json()["logs"]


def test_scraper_runs_database_lifecycle():
    """Verify scraper_runs table records run lifecycle."""
    run_id = create_scraper_run(
        user_id=77,
        portal="linkedin",
        days=1,
        queries="Bauingenieur, Statiker",
    )
    assert run_id > 0

    runs = get_user_scraper_runs(user_id=77)
    assert len(runs) >= 1
    assert runs[0]["queries"] == "Bauingenieur, Statiker"
    assert runs[0]["status"] == "running"

    # Update run to completed
    update_scraper_run(run_id, status="completed", jobs_scraped=12, jobs_matched=4)
    updated_runs = get_user_scraper_runs(user_id=77)
    assert updated_runs[0]["status"] == "completed"
    assert updated_runs[0]["jobs_scraped"] == 12
    assert updated_runs[0]["jobs_matched"] == 4
