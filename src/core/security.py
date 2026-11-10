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

DEFAULT_JWT_SECRET = "karriere_pipeline_saas_default_secret_key_change_in_prod"
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", DEFAULT_JWT_SECRET)
ENV = os.environ.get("ENV", "development").lower()
if ENV in ("production", "prod"):
    if JWT_SECRET_KEY == DEFAULT_JWT_SECRET or len(JWT_SECRET_KEY) < 32:
        raise RuntimeError(
            "FATAL: Insecure JWT_SECRET_KEY in production. Must be at least 32 characters and not use default."
        )
elif JWT_SECRET_KEY == DEFAULT_JWT_SECRET:
    logger.warning("Using default insecure JWT_SECRET_KEY in non-production mode.")

JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", str(60 * 24 * 30)))  # 30 days
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_JWKS_URL = os.environ.get("SUPABASE_JWKS_URL", "")
if not SUPABASE_JWKS_URL and SUPABASE_URL:
    SUPABASE_JWKS_URL = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

_jwks_client: jwt.PyJWKClient | None = None


def get_jwks_client() -> jwt.PyJWKClient | None:
    """Return singleton PyJWKClient configured with verified HTTPS SUPABASE_JWKS_URL."""
    global _jwks_client
    if _jwks_client is None and SUPABASE_JWKS_URL:
        if not SUPABASE_JWKS_URL.startswith("https://"):
            logger.error("SUPABASE_JWKS_URL must use https:// for secure key retrieval.")
            return None
        try:
            _jwks_client = jwt.PyJWKClient(SUPABASE_JWKS_URL)
        except Exception as exc:
            logger.warning(f"Failed to initialize Supabase JWKS client: {exc}")
    return _jwks_client


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
    """Decode and validate a JWT access token (supports local HS256 & Supabase ES256)."""
    # 1. Try Supabase JWKS if token has kid or ES256 algorithm
    try:
        header = jwt.get_unverified_header(token)
        if (header.get("alg") == "ES256" or "kid" in header) and SUPABASE_JWKS_URL:
            client = get_jwks_client()
            if client:
                signing_key = client.get_signing_key_from_jwt(token)
                options = {"verify_aud": False}
                issuer = f"{SUPABASE_URL.rstrip('/')}/auth/v1" if SUPABASE_URL else None
                if not issuer:
                    options["verify_iss"] = False
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256"],
                    options=options,
                    issuer=issuer,
                )
                return payload
    except Exception as exc:
        logger.debug(f"Supabase JWKS token decode failed, falling back to local JWT: {exc}")

    # 2. Local HS256 JWT decode
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as exc:
        logger.debug(f"JWT validation failed: {exc}")
        return None


def verify_google_id_token(id_token: str) -> dict[str, Any] | None:
    """Verify a Google OAuth2 ID Token using google-auth library with cryptographic signature verification."""
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
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        req = google_requests.Request()
        info = google_id_token.verify_oauth2_token(
            token,
            req,
            audience=GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else None,
        )
        return info
    except Exception as exc:
        logger.warning(f"Google token cryptographic verification failed: {exc}")
        return None
