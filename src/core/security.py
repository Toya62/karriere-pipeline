"""Authentication, password hashing, JWT tokens, and OAuth security utilities."""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from src.core.logger import get_logger

logger = get_logger(__name__)

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "karriere_pipeline_saas_default_secret_key_change_in_prod")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", str(60 * 24 * 30)))  # 30 days
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as exc:
        logger.warning(f"Password verification error: {exc}")
        return False


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as exc:
        logger.debug(f"JWT validation failed: {exc}")
        return None


def verify_google_id_token(id_token: str) -> dict[str, Any] | None:
    """Verify a Google OAuth2 ID Token using Google tokeninfo API or test mocks."""
    token = id_token.strip()
    if not token:
        return None

    # Test/Mock hook for unit tests: mock-google-token:email@test.com:User Name
    if token.startswith("mock-google-token:"):
        parts = token.split(":")
        email = parts[1] if len(parts) > 1 else "mock@test.com"
        name = parts[2] if len(parts) > 2 else "Mock User"
        sub = parts[3] if len(parts) > 3 else "mock-sub-123"
        return {"email": email, "name": name, "sub": sub, "email_verified": True}

    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
        req = urllib.request.Request(url, headers={"User-Agent": "Karriere-Pipeline-Auth"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                info = json.loads(body)
                if GOOGLE_CLIENT_ID and info.get("aud") != GOOGLE_CLIENT_ID:
                    logger.warning("Google token aud mismatch")
                    return None
                return info
    except urllib.error.HTTPError as http_err:
        logger.warning(f"Google tokeninfo HTTP error {http_err.code}: {http_err.reason}")
    except Exception as exc:
        logger.warning(f"Google token verification failed: {exc}")
    return None
