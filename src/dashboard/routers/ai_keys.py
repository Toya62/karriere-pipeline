"""
src/dashboard/routers/ai_keys.py

BYOK (Bring Your Own Key) management router for user-provided AI keys.
Provides secure CRUD endpoints with rate limiting, verification-before-store,
and masked reporting under /api/ai-keys.
"""

import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.key_vault import (
    decrypt_key,
    encrypt_key,
    fingerprint,
    validate_key_format,
)
from src.dashboard.routers.auth import require_authenticated_user
from src.db.database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-keys", tags=["AI Keys"])

# In-memory sliding window rate limiter: max 10 key modifications per user per hour
_KEY_RATE_LIMIT_WINDOW = 3600
_KEY_RATE_LIMIT_MAX = 10
_user_key_rate_limits: Dict[int, List[float]] = {}


def _check_key_rate_limit(user_id: int) -> None:
    now = time.time()
    attempts = _user_key_rate_limits.get(user_id, [])
    # purge old entries
    attempts = [t for t in attempts if now - t < _KEY_RATE_LIMIT_WINDOW]
    if len(attempts) >= _KEY_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: maximum 10 key operations per hour.",
        )
    attempts.append(now)
    _user_key_rate_limits[user_id] = attempts


def _get_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def test_gemini_key_live(key: str, timeout: int = 5) -> tuple[bool, str, int]:
    """Test a Gemini API key with a minimal generateContent ping.
    Returns (success, error_message, status_code).
    """
    model = "gemini-2.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_get_ssl_context()) as resp:
            if resp.status == 200:
                return True, "", 200
            return False, f"Unexpected response status: {resp.status}", resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        try:
            body = json.loads(exc.read().decode("utf-8", errors="ignore"))
            msg = body.get("error", {}).get("message", exc.reason)
        except Exception:
            msg = str(exc.reason or f"HTTP {code}")
        return False, msg, code
    except Exception as exc:
        return False, str(exc), 502


class AddKeyRequest(BaseModel):
    provider: str = Field(default="gemini", description="AI provider (v1: only 'gemini')")
    key: str = Field(..., min_length=10, max_length=128, description="API key plaintext")


class KeyResponse(BaseModel):
    provider: str
    status: str
    key_last4: str
    last_validated_at: Optional[str] = None
    created_at: Optional[str] = None
    last_error: Optional[str] = None


@router.get("", response_model=List[KeyResponse])
def list_user_keys(current_user: dict[str, Any] = Depends(require_authenticated_user)):
    """List stored AI keys for current user with masked credentials."""
    user_id = current_user["id"]
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT provider, status, key_last4, last_validated_at, created_at, last_error
        FROM user_ai_keys
        WHERE user_id = ?
        ORDER BY provider ASC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        KeyResponse(
            provider=r[0],
            status=r[1],
            key_last4=r[2],
            last_validated_at=str(r[3]) if r[3] else None,
            created_at=str(r[4]) if r[4] else None,
            last_error=r[5],
        )
        for r in rows
    ]


@router.get("/usage")
def get_user_ai_usage(current_user: dict[str, Any] = Depends(require_authenticated_user)):
    """Return user quota and usage metrics including BYOK."""
    from src.core.entitlements import get_user_usage_stats
    return get_user_usage_stats(current_user)


@router.post("", status_code=status.HTTP_201_CREATED)
def add_or_replace_key(
    req: AddKeyRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
):
    """Validate format and live credentials before encrypting and storing user key."""
    user_id = current_user["id"]
    _check_key_rate_limit(user_id)

    provider = req.provider.strip().lower()
    if provider != "gemini":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'gemini' provider is supported in v1.",
        )

    raw_key = req.key.strip()
    if not validate_key_format(provider, raw_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Gemini API key format. Key must start with 'AIza' and be 39 characters.",
        )

    # Validate before store
    is_valid, err_msg, status_code = test_gemini_key_live(raw_key)
    if not is_valid:
        if status_code in (400, 401, 403):
            logger.warning(f"User {user_id} supplied rejected Gemini key (HTTP {status_code}): {err_msg[:80]}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your Gemini key was rejected by Google ({status_code}): {err_msg}",
            )
        else:
            logger.error(f"Live validation failed with upstream error {status_code}: {err_msg[:80]}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not verify key with Google ({status_code}). Please try again later.",
            )

    # Encrypt and store
    ciphertext = encrypt_key(raw_key)
    fp = fingerprint(raw_key)
    last4 = raw_key[-4:]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Upsert pattern compatible with SQLite and Postgres
    cursor.execute(
        """
        SELECT id FROM user_ai_keys WHERE user_id = ? AND provider = ?
        """,
        (user_id, provider),
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            """
            UPDATE user_ai_keys
            SET key_ciphertext = ?, key_fingerprint = ?, key_last4 = ?,
                status = 'active', last_validated_at = CURRENT_TIMESTAMP,
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND provider = ?
            """,
            (ciphertext, fp, last4, user_id, provider),
        )
    else:
        cursor.execute(
            """
            INSERT INTO user_ai_keys (
                user_id, provider, key_ciphertext, key_fingerprint,
                key_last4, status, last_validated_at, last_error
            ) VALUES (?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, NULL)
            """,
            (user_id, provider, ciphertext, fp, last4),
        )

    conn.commit()
    conn.close()

    logger.info(f"User {user_id} successfully stored active key for provider '{provider}' (fp: {fp})")
    return {
        "success": True,
        "provider": provider,
        "status": "active",
        "key_last4": last4,
    }


@router.post("/{provider}/validate")
def validate_stored_key(
    provider: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
):
    """Re-test an existing stored key against upstream provider."""
    user_id = current_user["id"]
    provider = provider.strip().lower()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, key_ciphertext FROM user_ai_keys
        WHERE user_id = ? AND provider = ?
        """,
        (user_id, provider),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No key found for provider '{provider}'.",
        )

    key_id, ciphertext = row[0], row[1]
    try:
        raw_key = decrypt_key(ciphertext)
    except Exception as exc:
        cursor.execute(
            """
            UPDATE user_ai_keys
            SET status = 'invalid', last_error = 'Decryption failed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (key_id,),
        )
        conn.commit()
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stored key could not be decrypted. Please re-enter your key in Settings.",
        )

    is_valid, err_msg, status_code = test_gemini_key_live(raw_key)
    if is_valid:
        cursor.execute(
            """
            UPDATE user_ai_keys
            SET status = 'active', last_validated_at = CURRENT_TIMESTAMP,
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (key_id,),
        )
        conn.commit()
        conn.close()
        return {"valid": True, "status": "active"}

    # Validation failed
    new_status = "invalid" if status_code in (400, 401, 403) else "active"
    cursor.execute(
        """
        UPDATE user_ai_keys
        SET status = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_status, err_msg[:200], key_id),
    )
    conn.commit()
    conn.close()

    if status_code in (400, 401, 403):
        return {"valid": False, "status": "invalid", "error": err_msg}
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Provider returned error ({status_code}): {err_msg}",
    )


@router.delete("/{provider}")
def delete_user_key(
    provider: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
):
    """Permanently delete user's stored API key for provider."""
    user_id = current_user["id"]
    provider = provider.strip().lower()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM user_ai_keys
        WHERE user_id = ? AND provider = ?
        """,
        (user_id, provider),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No key found for provider '{provider}'.",
        )

    logger.info(f"User {user_id} revoked key for provider '{provider}'")
    return {"success": True, "message": f"{provider} key removed."}
