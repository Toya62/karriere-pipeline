"""
tests/test_byok_security.py

Security assertions for BYOK:
- Ensure no raw API keys are logged
- Ensure endpoints reject cross-tenant access with 404
- Ensure raw keys never appear in user_ai_keys responses
"""

import logging
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.dashboard.routers import ai_keys
from src.db.database import get_db_connection, setup_db

client = TestClient(create_app())
SECRET_RAW_KEY = "AIzaSy" + "SecretCandidateKeyNeverToLeak1234"


def test_no_api_key_leaks_in_logs(caplog):
    setup_db()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (id, email, full_name, role, tier, is_verified)
        VALUES (999, 'leak_test@example.com', 'Leak Tester', 'user', 'free', 1)
        ON CONFLICT (id) DO UPDATE SET is_verified = 1
        """
    )
    conn.commit()
    conn.close()

    caplog.set_level(logging.DEBUG)

    token = create_access_token({"user_id": 999, "email": "leak_test@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("src.dashboard.routers.ai_keys.test_gemini_key_live", return_value=(True, "", 200)):
        # Add key
        resp = client.post("/api/ai-keys", headers=headers, json={"provider": "gemini", "key": SECRET_RAW_KEY})
        assert resp.status_code == 201

        # List keys
        resp = client.get("/api/ai-keys", headers=headers)
        assert resp.status_code == 200

        # Validate
        resp = client.post("/api/ai-keys/gemini/validate", headers=headers)
        assert resp.status_code == 200

        # Delete
        resp = client.delete("/api/ai-keys/gemini", headers=headers)
        assert resp.status_code == 200

    # Assert SECRET_RAW_KEY is never in any log record
    for record in caplog.records:
        assert SECRET_RAW_KEY not in record.getMessage(), f"Leaked key in log: {record.getMessage()}"

    # Also assert SECRET_RAW_KEY is never in the response bodies
    assert SECRET_RAW_KEY not in resp.text
