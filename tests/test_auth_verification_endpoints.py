"""Integration tests for auth registration, verification token, and login gates."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.db.database import (
    create_user,
    create_verification_token,
    get_user_by_email,
    setup_db,
)
from src.core.security import hash_password

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def init_test_db():
    setup_db()


def test_register_creates_unverified_user_and_dispatches_email():
    import uuid
    email = f"reg_{uuid.uuid4().hex[:8]}@example.com"
    with patch("src.dashboard.routers.auth.send_verification_email", return_value=True) as mock_send:
        resp = client.post("/api/auth/register", json={
            "email": email,
            "password": "Password123!",
            "full_name": "New Candidate"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("requires_verification") is True
        assert mock_send.called

        u = get_user_by_email(email)
        assert u is not None
        assert u["is_verified"] in (False, 0)
        assert u["verification_token"] is not None


def test_login_blocked_if_unverified():
    import uuid
    email = f"blocked_{uuid.uuid4().hex[:8]}@example.com"
    create_user(
        email=email,
        hashed_password=hash_password("Secret123!"),
        full_name="Blocked Candidate",
        auth_provider="email",
        is_verified=False,
    )

    resp = client.post("/api/auth/login", json={
        "email": email,
        "password": "Secret123!"
    })
    assert resp.status_code == 403
    data = resp.json()
    assert data.get("error") == "email_unverified"


def test_verify_endpoint_activates_account_and_redirects():
    import uuid
    email = f"verify_{uuid.uuid4().hex[:8]}@example.com"
    u = create_user(
        email=email,
        hashed_password="hashed_pw",
        full_name="Verify Me",
        auth_provider="email",
        is_verified=False,
    )
    token = create_verification_token(u["id"])

    with patch("src.dashboard.routers.auth.send_welcome_email", return_value=True) as mock_welcome, \
         patch("src.dashboard.routers.auth.send_admin_new_user_alert", return_value=True) as mock_alert:
        resp = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
        assert resp.status_code in (302, 307)
        location = resp.headers.get("location", "")
        assert "verified=1" in location
        assert "token=" in location

        u_verified = get_user_by_email(email)
        assert u_verified["is_verified"] in (True, 1)
        assert u_verified["verification_token"] is None
        assert mock_welcome.called
        assert mock_alert.called


def test_resend_verification_endpoint():
    import uuid
    email = f"resend_{uuid.uuid4().hex[:8]}@example.com"
    create_user(
        email=email,
        hashed_password="hashed_pw",
        full_name="Resend Candidate",
        auth_provider="email",
        is_verified=False,
    )

    with patch("src.dashboard.routers.auth.send_verification_email", return_value=True) as mock_send:
        resp = client.post("/api/auth/resend-verification", json={"email": email})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert mock_send.called
