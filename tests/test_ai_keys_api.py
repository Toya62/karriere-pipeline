"""
tests/test_ai_keys_api.py

Unit and integration tests for /api/ai-keys endpoint:
- Auth required (401 without Bearer token)
- Format validation (reject non-Gemini or invalid Gemini keys)
- Live verification before store
- Masked responses (no raw keys or ciphertexts exposed)
- Cross-user tenant isolation (user A cannot see or delete user B's key)
- Rate limiting (max 10 POST operations per hour)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.dashboard.routers import ai_keys
from src.db.database import get_db_connection, setup_db

client = TestClient(create_app())

VALID_DUMMY_GEMINI_KEY = "AIzaSy" + "A" * 33


@pytest.fixture(autouse=True)
def setup_test_users_and_clean_keys():
    setup_db()
    ai_keys._user_key_rate_limits.clear()
    conn = get_db_connection()
    cur = conn.cursor()
    for uid in (100, 101, 102, 201, 202, 301):
        cur.execute(
            """
            INSERT INTO users (id, email, full_name, role, tier, is_verified)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT (id) DO UPDATE SET is_verified = 1
            """,
            (uid, f"test_user_{uid}@example.com", f"Test User {uid}", "user", "free"),
        )
    cur.execute("DELETE FROM user_ai_keys WHERE user_id >= 100")
    conn.commit()
    conn.close()


def test_auth_required():
    # No header
    resp = client.get("/api/ai-keys")
    assert resp.status_code == 401

    resp = client.post("/api/ai-keys", json={"provider": "gemini", "key": VALID_DUMMY_GEMINI_KEY})
    assert resp.status_code == 401


def test_format_validation():
    token = create_access_token({"user_id": 100, "email": "test_user_100@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    # Invalid provider
    resp = client.post("/api/ai-keys", headers=headers, json={"provider": "openai", "key": "sk-12345678901234567890"})
    assert resp.status_code == 400
    err = resp.json().get("error") or resp.json().get("detail")
    assert "Only 'gemini'" in err

    # Invalid format (wrong prefix)
    resp = client.post("/api/ai-keys", headers=headers, json={"provider": "gemini", "key": "BIzaSy" + "A" * 33})
    assert resp.status_code == 400
    err = resp.json().get("error") or resp.json().get("detail")
    assert "Invalid Gemini API key format" in err

    # Invalid format (too short)
    resp = client.post("/api/ai-keys", headers=headers, json={"provider": "gemini", "key": "AIzaSyShort"})
    assert resp.status_code == 400
    err = resp.json().get("error") or resp.json().get("detail")
    assert "Invalid Gemini API key format" in err


@patch("src.dashboard.routers.ai_keys.test_gemini_key_live")
def test_add_key_verification_failure(mock_test_key):
    token = create_access_token({"user_id": 101, "email": "test_user_101@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. 401 rejected by Google -> 400
    mock_test_key.return_value = (False, "API key not valid. Please pass a valid API key.", 401)
    resp = client.post("/api/ai-keys", headers=headers, json={"provider": "gemini", "key": VALID_DUMMY_GEMINI_KEY})
    assert resp.status_code == 400
    err = resp.json().get("error") or resp.json().get("detail")
    assert "rejected by Google (401)" in err

    # 2. 502 / upstream timeout -> 502
    mock_test_key.return_value = (False, "Service Unavailable", 503)
    resp = client.post("/api/ai-keys", headers=headers, json={"provider": "gemini", "key": VALID_DUMMY_GEMINI_KEY})
    assert resp.status_code == 502
    err = resp.json().get("error") or resp.json().get("detail")
    assert "Could not verify key with Google" in err


@patch("src.dashboard.routers.ai_keys.test_gemini_key_live")
def test_crud_and_masked_response(mock_test_key):
    mock_test_key.return_value = (True, "", 200)

    token = create_access_token({"user_id": 102, "email": "test_user_102@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Add key
    resp = client.post("/api/ai-keys", headers=headers, json={"provider": "gemini", "key": VALID_DUMMY_GEMINI_KEY})
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "active"
    assert data["key_last4"] == VALID_DUMMY_GEMINI_KEY[-4:]

    # 2. List keys - assert masked, no key leakage
    resp = client.get("/api/ai-keys", headers=headers)
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 1
    assert keys[0]["provider"] == "gemini"
    assert keys[0]["status"] == "active"
    assert keys[0]["key_last4"] == VALID_DUMMY_GEMINI_KEY[-4:]
    assert "key" not in keys[0]
    assert "key_ciphertext" not in keys[0]

    # 3. Validate stored key
    resp = client.post("/api/ai-keys/gemini/validate", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["valid"] is True

    # 4. Delete key
    resp = client.delete("/api/ai-keys/gemini", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 5. List keys is now empty
    resp = client.get("/api/ai-keys", headers=headers)
    assert resp.json() == []

    # 6. Delete again -> 404
    resp = client.delete("/api/ai-keys/gemini", headers=headers)
    assert resp.status_code == 404


@patch("src.dashboard.routers.ai_keys.test_gemini_key_live")
def test_cross_user_isolation(mock_test_key):
    mock_test_key.return_value = (True, "", 200)

    user1_headers = {"Authorization": f"Bearer {create_access_token({'user_id': 201, 'email': 'test_user_201@example.com'})}"}
    user2_headers = {"Authorization": f"Bearer {create_access_token({'user_id': 202, 'email': 'test_user_202@example.com'})}"}

    # User 1 stores key
    resp = client.post("/api/ai-keys", headers=user1_headers, json={"provider": "gemini", "key": VALID_DUMMY_GEMINI_KEY})
    assert resp.status_code == 201

    # User 2 lists keys -> empty!
    resp = client.get("/api/ai-keys", headers=user2_headers)
    assert resp.json() == []

    # User 2 cannot validate User 1's key
    resp = client.post("/api/ai-keys/gemini/validate", headers=user2_headers)
    assert resp.status_code == 404

    # User 2 cannot delete User 1's key
    resp = client.delete("/api/ai-keys/gemini", headers=user2_headers)
    assert resp.status_code == 404


@patch("src.dashboard.routers.ai_keys.test_gemini_key_live")
def test_rate_limiting(mock_test_key):
    mock_test_key.return_value = (True, "", 200)

    user_headers = {"Authorization": f"Bearer {create_access_token({'user_id': 301, 'email': 'test_user_301@example.com'})}"}

    # Execute 10 calls (allowed limit)
    for _ in range(10):
        resp = client.post("/api/ai-keys", headers=user_headers, json={"provider": "gemini", "key": VALID_DUMMY_GEMINI_KEY})
        assert resp.status_code == 201

    # 11th call exceeds limit -> 429
    resp = client.post("/api/ai-keys", headers=user_headers, json={"provider": "gemini", "key": VALID_DUMMY_GEMINI_KEY})
    assert resp.status_code == 429
    detail_msg = resp.json().get("error") or resp.json().get("detail", "")
    assert "Rate limit exceeded" in detail_msg

    # Validate endpoint also respects rate limit
    resp_val = client.post("/api/ai-keys/gemini/validate", headers=user_headers)
    assert resp_val.status_code == 429
    val_detail = resp_val.json().get("error") or resp_val.json().get("detail", "")
    assert "Rate limit exceeded" in val_detail
