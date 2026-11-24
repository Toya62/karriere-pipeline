"""Authentication, password hashing, JWT tokens, and OAuth security utilities."""

import os
import json
import secrets
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from src.core.logger import get_logger

logger = get_logger(__name__)

INSECURE_PLACEHOLDER_SECRETS = {
    "karriere_pipeline_saas_default_secret_key_change_in_prod",
    "change_this_to_a_secure_random_secret_in_production",
    "replace_with_a_secure_random_secret_at_least_32_chars",
    "secret",
    "changeme",
}

raw_secret = os.environ.get("JWT_SECRET_KEY", "").strip()
ENV = os.environ.get("ENV", "development").lower()

if ENV in ("production", "prod"):
    if not raw_secret or raw_secret in INSECURE_PLACEHOLDER_SECRETS or len(raw_secret) < 32:
        raise RuntimeError(
            "FATAL: Insecure or missing JWT_SECRET_KEY in production. Must be at least 32 characters and not a placeholder."
        )
    JWT_SECRET_KEY = raw_secret
else:
    if not raw_secret or raw_secret in INSECURE_PLACEHOLDER_SECRETS:
        # Generate an ephemeral secure random secret for this dev/test process if unset or placeholder
        JWT_SECRET_KEY = secrets.token_hex(32)
        logger.warning("No explicit JWT_SECRET_KEY set; generated ephemeral development secret.")
    else:
        JWT_SECRET_KEY = raw_secret

JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", str(60 * 24 * 30)))  # 30 days
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or os.environ.get("VITE_GOOGLE_CLIENT_ID") or ""
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

    if not GOOGLE_CLIENT_ID:
        logger.error("Google authentication failed: GOOGLE_CLIENT_ID is not configured.")
        return None

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        req = google_requests.Request()
        info = google_id_token.verify_oauth2_token(
            token,
            req,
            audience=GOOGLE_CLIENT_ID,
        )
        return info
    except Exception as exc:
        logger.warning(f"Google token cryptographic verification failed: {exc}")
        return None
