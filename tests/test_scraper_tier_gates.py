"""Unit tests for Scraper and Portal tier gating."""

import pytest
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.core.entitlements import record_usage

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def clean_usage():
    from src.db.database import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_usage WHERE user_id >= 100")
        conn.commit()
    finally:
        conn.close()


def test_free_user_cannot_scrape_pro_portals():
    import uuid
    from src.db.database import create_user
    email = f"free_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Free User", auth_provider="email", tier="free")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "free"})
    resp = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {token}"},
        json={"portal": "bund", "days": 1},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"] == "tier_restricted"
    assert "PRO" in data["message"]


def test_free_user_can_scrape_linkedin():
    import uuid
    from src.db.database import create_user
    email = f"free_li_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Free User", auth_provider="email", tier="free")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "free"})
    resp = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {token}"},
        json={"portal": "linkedin", "days": 1},
    )
    # Allowed through tier check (not 403)
    assert resp.status_code != 403


def test_free_user_daily_run_limit_blocked():
    import uuid
    from src.db.database import create_user
    email = f"free_limit_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Free User", auth_provider="email", tier="free")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "free"})
    # Consume 1 daily run
    record_usage(u["id"], "scraper_runs", 1)

    resp = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {token}"},
        json={"portal": "linkedin", "days": 1},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"] == "tier_limit_reached"
    assert "Daily scraper runs limit reached" in data["message"]


def test_pro_user_can_scrape_pro_portals():
    import uuid
    from src.db.database import create_user
    email = f"pro_scraper_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Pro User", auth_provider="email", tier="pro")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "pro"})
    resp = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {token}"},
        json={"portal": "bund", "days": 1},
    )
    assert resp.status_code != 403


def test_free_user_ai_matcher_quota_blocked():
    import uuid
    from src.db.database import create_user
    email = f"free_matcher_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Free User", auth_provider="email", tier="free")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "free"})
    # Consume 25 monthly AI evaluations
    record_usage(u["id"], "ai_evaluations", 25)

    resp = client.post(
        "/api/run-matcher",
        headers={"Authorization": f"Bearer {token}"},
        json={"max_age_days": 1},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"] == "tier_limit_reached"
    assert "Monthly ai evaluations limit reached" in data["message"]
