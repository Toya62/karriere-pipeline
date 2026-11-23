"""
src/core/key_vault.py

Cryptographic vault for encrypting and decrypting user-provided API keys (BYOK).
Uses Fernet (AES-128-CBC + HMAC-SHA256) with symmetric key configured via AI_KEYS_ENCRYPTION_KEY.
"""

import os
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

ENV_VAR_ENCRYPTION_KEY = "AI_KEYS_ENCRYPTION_KEY"
# Deterministic 32-byte url-safe base64 key reserved strictly for local testing & development
_DEV_FALLBACK_KEY = b"DGRI1gIT66_Lqa9RCWyr1DDTwspd_r0YxhidaZdNGqw="


def _is_production() -> bool:
    env = os.environ.get("ENV", "").strip().lower()
    return env in ("production", "prod")


def get_fernet_key() -> bytes:
    """Return the configured Fernet encryption key as bytes.
    Raises RuntimeError if unset in production.
    """
    raw = os.environ.get(ENV_VAR_ENCRYPTION_KEY, "").strip()
    if raw:
        return raw.encode("utf-8") if isinstance(raw, str) else raw
    if _is_production():
        raise RuntimeError(
            f"FATAL: {ENV_VAR_ENCRYPTION_KEY} environment variable must be set in production. "
            "Server cannot safely store or decrypt user API keys."
        )
    return _DEV_FALLBACK_KEY


def encrypt_key(plaintext: str, key: Optional[bytes] = None) -> str:
    """Encrypt a plaintext API key and return base64-encoded ciphertext."""
    if not plaintext or not plaintext.strip():
        raise ValueError("Cannot encrypt empty key")
    f = Fernet(key or get_fernet_key())
    token = f.encrypt(plaintext.strip().encode("utf-8"))
    return token.decode("utf-8")


def decrypt_key(ciphertext: str, key: Optional[bytes] = None) -> str:
    """Decrypt ciphertext and return plaintext API key.
    Raises InvalidToken on tampering, corruption, or key mismatch.
    """
    if not ciphertext or not ciphertext.strip():
        raise ValueError("Cannot decrypt empty ciphertext")
    f = Fernet(key or get_fernet_key())
    plaintext = f.decrypt(ciphertext.strip().encode("utf-8"))
    return plaintext.decode("utf-8")


def fingerprint(plaintext: str) -> str:
    """Return stable 12-char SHA-256 fingerprint of the key for dedup/logging."""
    if not plaintext or not plaintext.strip():
        return ""
    return hashlib.sha256(plaintext.strip().encode("utf-8")).hexdigest()[:12]


def validate_key_format(provider: str, key: str) -> bool:
    """Validate format before testing or storing.
    Gemini keys are AIza... and exactly 39 characters.
    """
    clean = key.strip() if key else ""
    if provider.lower() == "gemini":
        return clean.startswith("AIza") and len(clean) == 39
    return len(clean) >= 20
