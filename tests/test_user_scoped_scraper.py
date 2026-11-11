"""Unit tests for user-scoped scraper CLI and API endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard import state
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, get_user_by_email, update_user, setup_db


@pytest.fixture(autouse=True)
def reset_scraper_state():
    state.SCRAPER_PROCESS = None
    state.MATCHER_PROCESS = None
    state.USER_SCRAPER_PROCESSES.clear()
    state.USER_MATCHER_PROCESSES.clear()
    state.USER_SCRAPER_RUN_IDS.clear()
    yield
    state.SCRAPER_PROCESS = None
    state.MATCHER_PROCESS = None
    state.USER_SCRAPER_PROCESSES.clear()
    state.USER_MATCHER_PROCESSES.clear()
    state.USER_SCRAPER_RUN_IDS.clear()


@pytest.fixture
def test_client():
    setup_db()
    return TestClient(app)


@pytest.fixture
def auth_headers():
    u = get_user_by_email("civil@example.com")
    if not u:
        u = create_user(
            email="civil@example.com",
            hashed_password="hashed_pw",
            full_name="Civil Engineer",
            auth_provider="email",
            role="candidate",
            tier="pro",
            is_verified=True,
        )
    else:
        update_user(u["id"], {"tier": "pro", "is_verified": True})
    token = create_access_token({"sub": f"user_{u['id']}", "user_id": u["id"], "id": u["id"], "email": u["email"], "role": "candidate"})
    return {"Authorization": f"Bearer {token}"}


def test_api_run_scraper_passes_user_id(test_client, auth_headers):
    with patch("src.dashboard.routers.scraper.subprocess.Popen") as mock_popen, \
         patch("src.dashboard.routers.scraper.get_user_profile") as mock_profile:

        mock_profile.return_value = {
            "target_titles": ["Bauingenieur", "Statiker"],
            "archetype": "civil_engineering",
        }
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        resp = test_client.post(
            "/api/run-scraper",
            json={"portal": "linkedin", "days": 1},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "--user-id" in cmd
        user_id_arg = cmd[cmd.index("--user-id") + 1]
        assert int(user_id_arg) > 0
        assert "--run-id" in cmd
        run_id_arg = cmd[cmd.index("--run-id") + 1]
        assert int(run_id_arg) > 0
        assert "--no-match" not in cmd


def test_api_run_scraper_auto_match_false(test_client, auth_headers):
    with patch("src.dashboard.routers.scraper.subprocess.Popen") as mock_popen, \
         patch("src.dashboard.routers.scraper.get_user_profile") as mock_profile:

        mock_profile.return_value = {
            "target_titles": ["Bauingenieur"],
            "archetype": "civil_engineering",
        }
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        resp = test_client.post(
            "/api/run-scraper",
            json={"portal": "linkedin", "days": 1, "auto_match": False},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "--no-match" in cmd


def test_cli_scrape_resolves_user_queries():
    from main import handle_scrape
    import argparse

    args = argparse.Namespace(
        portal="linkedin",
        days=1,
        no_match=True,
        no_generate=True,
        user_id=101,
    )

    with patch("main.get_user_profile") as mock_profile, \
         patch("main.run_scrape_linkedin") as mock_scrape:

        mock_profile.return_value = {
            "target_titles": ["Bauingenieur", "Statiker"],
            "archetype": "civil_engineering",
        }

        handle_scrape(args)

        assert mock_scrape.called
        # Check that queries passed were built from civil engineering profile
        queries_called = mock_scrape.call_args[1].get("queries")
        assert queries_called is not None
        assert any("Bauingenieur" in q for q in queries_called)


def test_scraper_runs_update_and_stale_cleanup():
    from src.db.database import (
        create_scraper_run,
        update_scraper_run,
        get_user_scraper_runs,
        cleanup_stale_scraper_runs,
        get_db_connection,
    )
    run_id = create_scraper_run(
        user_id=1,
        portal="linkedin",
        days=1,
        queries="Civil Engineer",
    )
    assert run_id > 0

    # Test update
    ok = update_scraper_run(
        run_id=run_id,
        status="completed",
        jobs_scraped=15,
        jobs_matched=12,
    )
    assert ok is True

    runs = get_user_scraper_runs(user_id=1, limit=5)
    target = next((r for r in runs if r["id"] == run_id), None)
    assert target is not None
    assert target["status"] == "completed"
    assert target["jobs_scraped"] == 15
    assert target["jobs_matched"] == 12
    assert target["scraped_count"] == 15
    assert target["approved_count"] == 12
    assert target["completed_at"] is not None

    # Test cleanup of older running runs
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scraper_runs (user_id, portal, days, queries, status, started_at) VALUES (1, 'indeed', 1, 'Test', 'running', '2026-01-01 00:00:00')"
    )
    conn.commit()
    conn.close()

    cleaned = cleanup_stale_scraper_runs(timeout_hours=1)
    assert cleaned >= 1
