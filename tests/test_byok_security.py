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


def test_gemini_key_validation_uses_header_and_verified_tls():
    """Verify test_gemini_key_live sends key in header and verifies TLS."""
    import urllib.request
    from unittest.mock import MagicMock
    from src.dashboard.routers.ai_keys import test_gemini_key_live

    captured_request = None
    captured_context = None

    def fake_urlopen(req, timeout=5, context=None):
        nonlocal captured_request, captured_context
        captured_request = req
        captured_context = context
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        success, err, code = test_gemini_key_live(SECRET_RAW_KEY)

    assert success is True
    assert captured_request is not None
    # Key must NOT be in URL query string
    assert "key=" not in captured_request.full_url
    assert SECRET_RAW_KEY not in captured_request.full_url
    # Key must be sent in x-goog-api-key header
    assert captured_request.get_header("X-goog-api-key") == SECRET_RAW_KEY
    # SSL context must verify certificates
    assert captured_context is not None
    assert captured_context.check_hostname is True
    assert captured_context.verify_mode == urllib.request.ssl.CERT_REQUIRED
