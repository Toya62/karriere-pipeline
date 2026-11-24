"""
tests/test_byok_router.py

Unit and regression tests for AIRouter BYOK key resolution and per-user failure isolation.
Asserts:
- User key is prioritized over server keys
- Server Gemini keys are untouched when user BYOK key is used
- 401/403 on user key marks user_ai_keys row invalid and does not fall back to server Gemini
- 401/403 on user key does not poison global _dead_gemini_keys
- user_id=None behaves identically to legacy server key operation
"""

import urllib.error
import pytest
from unittest.mock import patch, MagicMock

from src.ai.router import AIRouter, get_ai_router, route_ai_evaluation
from src.core.key_vault import encrypt_key, fingerprint
from src.db.database import get_db_connection, setup_db

USER_ID = 501
DUMMY_USER_KEY = "AIzaSyUserBYOKKeyForTesting1234567890"
DUMMY_SERVER_KEY = "AIzaSyServerKeyForTesting1234567890"


@pytest.fixture(autouse=True)
def setup_db_and_user():
    setup_db()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (id, email, full_name, role, tier, is_verified)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT (id) DO UPDATE SET is_verified = 1
        """,
        (USER_ID, "byok_tester@example.com", "BYOK Tester", "user", "free"),
    )
    cur.execute("DELETE FROM user_ai_keys WHERE user_id = ?", (USER_ID,))
    conn.commit()
    conn.close()


def _store_user_byok_key(key: str = DUMMY_USER_KEY, status: str = "active"):
    conn = get_db_connection()
    cur = conn.cursor()
    cipher = encrypt_key(key)
    fp = fingerprint(key)
    cur.execute(
        """
        INSERT INTO user_ai_keys (
            user_id, provider, key_ciphertext, key_fingerprint,
            key_last4, status, last_validated_at, last_error
        ) VALUES (?, 'gemini', ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)
        """,
        (USER_ID, cipher, fp, key[-4:], status),
    )
    conn.commit()
    conn.close()


def test_user_key_used_before_server_key():
    _store_user_byok_key(DUMMY_USER_KEY)

    router = AIRouter()
    router.keys["gemini"] = [DUMMY_SERVER_KEY]

    with patch.object(router, "_call_gemini", return_value="BYOK success") as mock_gemini:
        res = router.generate_content("hello", user_id=USER_ID)
        assert res == "BYOK success"
        assert router.last_key_origin == "byok"
        assert "gemini-byok" in router.last_provider_used
        # Assert _call_gemini called with user's key, NOT server key
        assert mock_gemini.call_args[1]["key"] == DUMMY_USER_KEY


def test_server_key_used_when_no_user_id_or_no_byok_key():
    router = AIRouter()
    router.keys["gemini"] = [DUMMY_SERVER_KEY]

    with patch.object(router, "_call_gemini", return_value="Server success") as mock_gemini:
        # 1. user_id is None
        res1 = router.generate_content("hello", user_id=None)
        assert res1 == "Server success"
        assert router.last_key_origin == "server"
        assert mock_gemini.call_args[1]["key"] == DUMMY_SERVER_KEY

        # 2. user has no key row
        res2 = router.generate_content("hello", user_id=USER_ID)
        assert res2 == "Server success"
        assert router.last_key_origin == "server"
        assert mock_gemini.call_args[1]["key"] == DUMMY_SERVER_KEY


def test_user_key_401_marks_invalid_and_skips_server_gemini():
    _store_user_byok_key(DUMMY_USER_KEY)

    router = AIRouter()
    router.keys["gemini"] = [DUMMY_SERVER_KEY]
    router.keys["groq"] = ["dummy-groq-key"]

    http_401 = urllib.error.HTTPError(
        url="https://generativelanguage.googleapis.com",
        code=401,
        msg="Unauthorized",
        hdrs=MagicMock(),
        fp=MagicMock(read=MagicMock(return_value=b'{"error":{"message":"API key not valid."}}')),
    )

    with patch.object(router, "_call_gemini", side_effect=http_401) as mock_gemini, \
         patch.object(router, "_call_groq", return_value="Groq fallback output") as mock_groq:
        res = router.generate_content("hello", user_id=USER_ID)
        assert res == "Groq fallback output"
        # Verify server Gemini was NEVER called
        called_keys = [call[1]["key"] for call in mock_gemini.call_args_list]
        assert DUMMY_SERVER_KEY not in called_keys
        # Verify user key was NOT added to server dead keys
        assert DUMMY_USER_KEY not in router._dead_gemini_keys
        assert DUMMY_SERVER_KEY not in router._dead_gemini_keys

    # Verify database status changed to 'invalid'
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, last_error FROM user_ai_keys WHERE user_id = ?", (USER_ID,))
    row = cur.fetchone()
    conn.close()
    assert row[0] == "invalid"
    assert "HTTP 401" in row[1]


def test_user_key_429_skips_server_gemini():
    _store_user_byok_key(DUMMY_USER_KEY)

    router = AIRouter()
    router.keys["gemini"] = [DUMMY_SERVER_KEY]
    router.keys["groq"] = ["dummy-groq-key"]

    http_429 = urllib.error.HTTPError(
        url="https://generativelanguage.googleapis.com",
        code=429,
        msg="Too Many Requests",
        hdrs=MagicMock(),
        fp=MagicMock(read=MagicMock(return_value=b'{"error":{"message":"Quota exceeded."}}')),
    )

    with patch.object(router, "_call_gemini", side_effect=http_429) as mock_gemini, \
         patch.object(router, "_call_groq", return_value="Groq fallback after 429"):
        res = router.generate_content("hello", user_id=USER_ID)
        assert res == "Groq fallback after 429"
        called_keys = [call[1]["key"] for call in mock_gemini.call_args_list]
        assert DUMMY_SERVER_KEY not in called_keys
        # Key status remains active on 429 (rate limit is temporary)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status FROM user_ai_keys WHERE user_id = ?", (USER_ID,))
        status = cur.fetchone()[0]
        conn.close()
        assert status == "active"


def test_corrupt_ciphertext_marks_invalid_and_falls_back_to_server():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_ai_keys (
            user_id, provider, key_ciphertext, key_fingerprint,
            key_last4, status, last_validated_at, last_error
        ) VALUES (?, 'gemini', 'corrupted-ciphertext', 'invalid12345', '1234', 'active', CURRENT_TIMESTAMP, NULL)
        """,
        (USER_ID,),
    )
    conn.commit()
    conn.close()

    router = AIRouter()
    router.keys["gemini"] = [DUMMY_SERVER_KEY]

    with patch.object(router, "_call_gemini", return_value="Server fallback success") as mock_gemini:
        res = router.generate_content("hello", user_id=USER_ID)
        assert res == "Server fallback success"
        assert mock_gemini.call_args[1]["key"] == DUMMY_SERVER_KEY

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, last_error FROM user_ai_keys WHERE user_id = ?", (USER_ID,))
    row = cur.fetchone()
    conn.close()
    assert row[0] == "invalid"
    assert "Decryption failed" in row[1]
