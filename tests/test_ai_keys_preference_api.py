"""Tests for /api/ai-keys/preference API endpoints."""

import uuid
import pytest
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, update_user_tier


@pytest.fixture
def auth_user():
    email = f"pref_api_{uuid.uuid4().hex[:8]}@example.com"
    user = create_user(email, "pw123", full_name="Pref API Tester")
    token = create_access_token({
        "sub": f"user_{user['id']}",
        "user_id": user["id"],
        "id": user["id"],
        "email": user["email"],
        "role": user.get("role", "candidate"),
    })
    return user, {"Authorization": f"Bearer {token}"}


def test_get_preference_unauthorized():
    client = TestClient(app)
    resp = client.get("/api/ai-keys/preference")
    assert resp.status_code == 401


def test_get_and_put_preference_success(auth_user):
    user, headers = auth_user
    client = TestClient(app)

    # Free user gets preference
    resp = client.get("/api/ai-keys/preference", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "preference" in data
    assert "tier" in data

    # Update preference to byok
    resp_put = client.put("/api/ai-keys/preference", json={"preference": "byok"}, headers=headers)
    assert resp_put.status_code == 200
    assert resp_put.json()["preference"] == "byok"

    # Confirm GET returns updated preference
    resp_get2 = client.get("/api/ai-keys/preference", headers=headers)
    assert resp_get2.json()["preference"] == "byok"


def test_put_preference_invalid_value(auth_user):
    user, headers = auth_user
    client = TestClient(app)

    resp = client.put("/api/ai-keys/preference", json={"preference": "invalid_pref"}, headers=headers)
    assert resp.status_code in (400, 422)
