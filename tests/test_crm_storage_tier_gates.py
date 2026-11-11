"""Unit tests for CRM job limits and storage tier gating."""

import base64
import uuid
import pytest
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.core.entitlements import record_usage
from src.db.database import create_user

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def clean_usage():
    from src.db.database import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_usage WHERE user_id >= 300")
        conn.commit()
    finally:
        conn.close()


def test_free_user_crm_job_cap():
    email = f"free_crm_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Free CRM User", auth_provider="email", tier="free")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "free"})

    # Fill CRM to 25 jobs
    for _ in range(25):
        record_usage(u["id"], "crm_jobs", 1)

    resp = client.post(
        "/api/applications",
        headers={"Authorization": f"Bearer {token}"},
        json={"company": "Cap Corp", "position": "Developer", "job_url": "https://example.com/job26"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"] == "tier_limit_reached"
    assert "CRM capacity limit reached" in data["message"]


def test_pro_user_unlimited_crm_jobs():
    email = f"pro_crm_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Pro CRM User", auth_provider="email", tier="pro")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "pro"})

    # Fill beyond 25
    record_usage(u["id"], "crm_jobs", 50)

    resp = client.post(
        "/api/applications",
        headers={"Authorization": f"Bearer {token}"},
        json={"company": "Pro Corp", "position": "Lead Dev", "job_url": "https://example.com/projob"},
    )
    assert resp.status_code != 403
