"""Unit tests for SaaS Authentication system (/api/auth)."""

import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app
from src.core.security import decode_access_token

client = TestClient(create_app())


def test_auth_registration_lifecycle():
    uid = uuid.uuid4().hex[:8]
    email = f"testuser_{uid}@example.com"
    password = "securePassword123!"

    # 1. Register
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Test Candidate"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data.get("requires_verification") is True
    assert data["user"]["email"] == email
    assert data["user"]["full_name"] == "Test Candidate"
    assert "hashed_password" not in data["user"]

    # 2. Duplicate registration rejected
    dup_resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Duplicate"},
    )
    assert dup_resp.status_code == 409
    msg = dup_resp.json().get("error") or dup_resp.json().get("detail") or ""
    assert "already exists" in msg

    # 3. Unverified login blocked
    unverified_resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert unverified_resp.status_code == 403
    assert unverified_resp.json().get("error") == "email_unverified"

    # 4. Verify user via verification token
    from src.db.database import get_user_by_email, verify_user_token
    user_record = get_user_by_email(email)
    assert user_record["verification_token"] is not None
    verify_user_token(user_record["verification_token"])

    # 5. Login with correct password after verification
    login_resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert "token" in login_data
    token = login_data["token"]

    # 6. Login with wrong password
    bad_resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert bad_resp.status_code == 401

    # 5. Get current user profile via /me
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["user"]["email"] == email

    # 6. Update user full_name
    update_resp = client.put(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "Updated Candidate Name"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["user"]["full_name"] == "Updated Candidate Name"


def test_auth_google_oauth_mock():
    uid = uuid.uuid4().hex[:8]
    email = f"oauth_{uid}@gmail.com"
    with patch("src.dashboard.routers.auth.verify_google_id_token") as mock_verify:
        mock_verify.return_value = {
            "email": email,
            "name": "OAuth Candidate",
            "sub": f"google-sub-{uid}",
            "email_verified": True,
        }
        resp = client.post("/api/auth/google", json={"credential": "fake_id_token_xyz"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert "token" in data
        assert data["user"]["email"] == email
        assert data["user"]["full_name"] == "OAuth Candidate"
        assert data["user"]["auth_provider"] == "google"

        # Decoding token reveals correct user_id
        payload = decode_access_token(data["token"])
        assert payload is not None
        assert payload["email"] == email


def test_auth_invalid_token():
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_gibberish_token"})
    assert resp.status_code == 401


def test_supabase_token_auto_provision(monkeypatch):
    """Verify that a verified Supabase JWT automatically provisions local user record."""
    test_sub = f"sb-sub-{uuid.uuid4().hex[:8]}"
    test_email = f"supabase_user_{uuid.uuid4().hex[:8]}@example.com"
    fake_payload = {
        "sub": test_sub,
        "email": test_email,
        "aud": "authenticated",
        "user_metadata": {"full_name": "Supabase Candidate"},
        "app_metadata": {"provider": "google"},
    }
    monkeypatch.setattr(
        "src.dashboard.routers.auth.decode_access_token",
        lambda token: fake_payload if token == "fake-supabase-jwt" else None,
    )
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer fake-supabase-jwt"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["email"] == test_email
    assert data["user"]["full_name"] == "Supabase Candidate"
    assert data["user"]["google_id"] == test_sub
