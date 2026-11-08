"""End-to-end integration test for candidate onboarding, verification, and session lifecycle."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.db.database import setup_db, get_user_by_email

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def init_db():
    setup_db()


def test_full_candidate_registration_verification_and_welcome_flow():
    import uuid
    email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"
    full_name = "E2E Candidate"

    # 1. Register with email & password -> unverified
    with patch("src.dashboard.routers.auth.send_verification_email", return_value=True) as mock_ver_email:
        reg_resp = client.post("/api/auth/register", json={
            "email": email,
            "password": password,
            "full_name": full_name,
        })
        assert reg_resp.status_code == 200
        data = reg_resp.json()
        assert data["success"] is True
        assert data["requires_verification"] is True
        assert mock_ver_email.called
        token = mock_ver_email.call_args[1].get("token") or mock_ver_email.call_args[0][2]
        assert token is not None

    # 2. Login fails before verification
    login_fail = client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    assert login_fail.status_code == 403
    assert login_fail.json()["error"] == "email_unverified"

    # 3. Verify via link
    with patch("src.dashboard.routers.auth.send_welcome_email", return_value=True) as mock_welcome, \
         patch("src.dashboard.routers.auth.send_admin_new_user_alert", return_value=True) as mock_admin:
        ver_resp = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
        assert ver_resp.status_code in (302, 307)
        location = ver_resp.headers["location"]
        assert "verified=1" in location
        assert "token=" in location
        assert mock_welcome.called
        assert mock_admin.called

    # 4. Login succeeds after verification
    login_success = client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    assert login_success.status_code == 200
    login_data = login_success.json()
    assert "token" in login_data
    assert login_data["user"]["email"] == email
    assert login_data["user"]["is_verified"] in (True, 1)

    # 5. Access protected /api/auth/me with session
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login_data['token']}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["email"] == email
