"""End-to-end integration test for Free vs Pro tier lifecycle and dynamic upgrade."""

import uuid
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.db.database import get_user_by_email, update_user

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def clean_usage():
    from src.db.database import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_usage WHERE user_id >= 500")
        conn.commit()
    finally:
        conn.close()


def test_full_tier_lifecycle_free_to_pro_upgrade():
    # 1. User registers as candidate
    from src.db.database import update_user
    from src.core.security import create_access_token
    email = f"tier_lifecycle_{uuid.uuid4().hex[:8]}@test.com"
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123!", "full_name": "Lifecycle Candidate"},
    )
    assert reg_resp.status_code == 200, reg_resp.text
    cand_data = reg_resp.json()
    cand_id = cand_data["user"]["id"]
    update_user(cand_id, {"is_verified": True})
    cand_token = create_access_token({"user_id": cand_id, "email": email, "role": "candidate"})
    assert cand_data["user"]["tier"] == "free"

    # 2. Free candidate attempts to run Bund.de scraper -> 403
    scrape_bund = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {cand_token}"},
        json={"portal": "bund", "days": 1},
    )
    assert scrape_bund.status_code == 403
    assert scrape_bund.json()["error"] == "tier_restricted"

    # 3. Free candidate runs LinkedIn scraper -> accepted (not 403)
    scrape_li = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {cand_token}"},
        json={"portal": "linkedin", "days": 1},
    )
    assert scrape_li.status_code != 403

    # 4. Generate applications: 3 allowed on Free, 4th blocked
    from src.core.entitlements import record_usage
    for _ in range(3):
        record_usage(cand_id, "applications", 1)

    app_4 = client.post(
        "/api/generate-application",
        headers={"Authorization": f"Bearer {cand_token}"},
        json={
            "company": "Quota AG",
            "position": "Backend Engineer",
            "description": "Building microservices with Python, FastAPI, and PostgreSQL for financial platform.",
        },
    )
    assert app_4.status_code == 403
    assert app_4.json()["error"] == "tier_limit_reached"

    # 5. Admin promotes user to PRO
    admin_user = get_user_by_email("pandeytoya22@gmail.com")
    if admin_user:
        admin_token = create_access_token({"user_id": admin_user["id"], "email": admin_user["email"], "role": "admin"})
    else:
        update_user(cand_id, {"role": "admin"})
        admin_token = cand_token

    promo_resp = client.post(
        "/api/auth/set-tier",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": email, "tier": "pro"},
    )
    assert promo_resp.status_code == 200
    assert promo_resp.json()["tier"] == "pro"

    # 6. Promoted PRO user can now scrape Bund.de and generate 4th application
    scrape_bund_pro = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {cand_token}"},
        json={"portal": "bund", "days": 1},
    )
    assert scrape_bund_pro.status_code != 403

    app_4_pro = client.post(
        "/api/generate-application",
        headers={"Authorization": f"Bearer {cand_token}"},
        json={
            "company": "Pro AG",
            "position": "Backend Engineer",
            "description": "Building microservices with Python, FastAPI, and PostgreSQL for financial platform.",
        },
    )
    assert app_4_pro.status_code != 403
