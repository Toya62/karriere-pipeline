"""Unit tests for SaaS Authentication system (/api/auth)."""

import uuid
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
    assert "token" in data
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

    # 3. Login with correct password
    login_resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert "token" in login_data
    token = login_data["token"]

    # 4. Login with wrong password
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
    # Mock token format: mock-google-token:<email>:<name>:<sub_id>
    mock_token = f"mock-google-token:{email}:OAuth Candidate:google-sub-{uid}"

    resp = client.post("/api/auth/google", json={"credential": mock_token})
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
