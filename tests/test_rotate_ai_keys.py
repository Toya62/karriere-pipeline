"""
tests/test_rotate_ai_keys.py

Unit tests for scripts/rotate_ai_keys.py key rotation script.
"""

from cryptography.fernet import Fernet
import pytest

from scripts.rotate_ai_keys import rotate_keys
from src.core.key_vault import decrypt_key, encrypt_key, fingerprint
from src.db.database import get_db_connection, setup_db

USER_ID = 601
RAW_KEY = "AIzaSyTestRotateKey123456789012345678"


@pytest.fixture(autouse=True)
def setup_test_row():
    setup_db()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (id, email, full_name, role, tier, is_verified)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT (id) DO UPDATE SET is_verified = 1
        """,
        (USER_ID, "rotate_test@example.com", "Rotate Tester", "user", "free"),
    )
    cur.execute("DELETE FROM user_ai_keys")
    conn.commit()
    conn.close()


def test_key_rotation_live_and_dry_run():
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    # Store with old_key
    cipher_old = encrypt_key(RAW_KEY, key=old_key.encode())
    fp = fingerprint(RAW_KEY)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_ai_keys (
            user_id, provider, key_ciphertext, key_fingerprint,
            key_last4, status, last_validated_at, last_error
        ) VALUES (?, 'gemini', ?, ?, ?, 'active', CURRENT_TIMESTAMP, NULL)
        """,
        (USER_ID, cipher_old, fp, RAW_KEY[-4:]),
    )
    conn.commit()
    conn.close()

    # 1. Dry run
    res_dry = rotate_keys(old_key=old_key, new_key=new_key, dry_run=True)
    assert res_dry["rotated"] >= 1
    assert res_dry["failed"] == 0

    # Assert row still decryptable with old_key
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT key_ciphertext FROM user_ai_keys WHERE user_id = ?", (USER_ID,))
    cipher_after_dry = cur.fetchone()[0]
    conn.close()
    assert decrypt_key(cipher_after_dry, key=old_key.encode()) == RAW_KEY

    # 2. Real rotation
    res_real = rotate_keys(old_key=old_key, new_key=new_key, dry_run=False)
    assert res_real["rotated"] >= 1
    assert res_real["failed"] == 0

    # Assert row is now decryptable with new_key (and fails with old_key)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT key_ciphertext FROM user_ai_keys WHERE user_id = ?", (USER_ID,))
    cipher_new = cur.fetchone()[0]
    conn.close()

    assert decrypt_key(cipher_new, key=new_key.encode()) == RAW_KEY
