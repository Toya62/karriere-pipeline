"""Unit tests for Application Generation and Copilot tier quotas."""

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
        cur.execute("DELETE FROM user_usage WHERE user_id >= 200")
        conn.commit()
    finally:
        conn.close()


def test_free_user_blocked_after_monthly_applications_quota():
    email = f"free_doc_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Free Doc User", auth_provider="email", tier="free")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "free"})
    # Consume free quota of 3
    for _ in range(3):
        record_usage(u["id"], "applications", 1)

    resp = client.post(
        "/api/generate-application",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "company": "Test AG",
            "position": "Software Engineer",
            "description": "A long job description requiring Python and SQL software engineering skills.",
        },
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"] == "tier_limit_reached"
    assert "Monthly applications limit reached" in data["message"]


def test_free_user_copilot_question_limit():
    email = f"free_copilot_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Free Copilot User", auth_provider="email", tier="free")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "free"})
    for _ in range(5):
        record_usage(u["id"], "form_copilot", 1)

    resp = client.post(
        "/api/answer-form-question",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Why do you want to work here?", "company": "Test Corp"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"] == "tier_limit_reached"
    assert "Monthly form copilot limit reached" in data["message"]


def test_pro_user_unlimited_applications():
    email = f"pro_doc_{uuid.uuid4().hex[:8]}@test.com"
    u = create_user(email, "Pro Doc User", auth_provider="email", tier="pro")
    token = create_access_token({"user_id": u["id"], "email": u["email"], "role": "user", "tier": "pro"})
    record_usage(u["id"], "applications", 50)

    # Calling copilot or generate doesn't hit 403
    resp = client.post(
        "/api/generate-application",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "company": "Pro AG",
            "position": "Senior Backend Developer",
            "description": "A long job description requiring Python, FastAPI, and Kubernetes infrastructure.",
        },
    )
    assert resp.status_code != 403
