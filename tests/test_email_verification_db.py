"""Unit tests for user email verification database schema and token lifecycle."""

import pytest
from src.db.database import (
    create_user,
    get_user_by_email,
    create_verification_token,
    verify_user_token,
    get_db_connection,
    setup_db,
)


@pytest.fixture(autouse=True)
def clean_users():
    setup_db()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email LIKE '%@token-test.com' OR email LIKE 'unverified_%@example.com' OR email LIKE 'token_test_%@example.com'")
        conn.commit()
    finally:
        conn.close()


def test_user_created_with_verification_status():
    import uuid
    email = f"unverified_{uuid.uuid4().hex[:8]}@example.com"
    u = create_user(
        email=email,
        hashed_password="hashed_pw",
        full_name="Test Unverified",
        auth_provider="email",
        role="candidate",
        tier="free",
        is_verified=False,
    )
    assert u["is_verified"] in (False, 0)

    google_email = f"google_{uuid.uuid4().hex[:8]}@token-test.com"
    u_google = create_user(
        email=google_email,
        full_name="Google User",
        auth_provider="google",
        google_id=f"gid_{uuid.uuid4().hex[:8]}",
        is_verified=True,
    )
    assert u_google["is_verified"] in (True, 1)


def test_verification_token_lifecycle():
    import uuid
    email = f"token_test_{uuid.uuid4().hex[:8]}@example.com"
    u = create_user(email, "hashed_pw", "Token User", auth_provider="email", is_verified=False)
    token = create_verification_token(u["id"])
    assert token and len(token) >= 32

    # Verify token activates user
    verified_user = verify_user_token(token)
    assert verified_user is not None
    assert verified_user["id"] == u["id"]
    assert verified_user["is_verified"] in (True, 1)

    # Re-using the same token fails
    assert verify_user_token(token) is None
