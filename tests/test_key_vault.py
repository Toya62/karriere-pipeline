"""
tests/test_key_vault.py

Unit tests for cryptographic key vault (BYOK encryption/decryption).
"""

import pytest
from cryptography.fernet import Fernet, InvalidToken
from src.core.key_vault import (
    encrypt_key,
    decrypt_key,
    fingerprint,
    validate_key_format,
    get_fernet_key,
    ENV_VAR_ENCRYPTION_KEY,
)


def test_roundtrip_encryption_decryption():
    raw_key = "AIzaSyDummyTestKeyForVerification12345"
    encrypted = encrypt_key(raw_key)
    assert encrypted != raw_key
    assert len(encrypted) > len(raw_key)

    decrypted = decrypt_key(encrypted)
    assert decrypted == raw_key


def test_wrong_key_fails_decryption():
    custom_key1 = Fernet.generate_key()
    custom_key2 = Fernet.generate_key()

    raw_key = "AIzaSyDummyTestKeyForVerification12345"
    encrypted = encrypt_key(raw_key, key=custom_key1)

    with pytest.raises(InvalidToken):
        decrypt_key(encrypted, key=custom_key2)


def test_tampered_ciphertext_fails():
    raw_key = "AIzaSyDummyTestKeyForVerification12345"
    encrypted = encrypt_key(raw_key)

    tampered = encrypted[:-4] + "aaaa"
    with pytest.raises(InvalidToken):
        decrypt_key(tampered)


def test_fingerprint_stable_and_truncated():
    key1 = "AIzaSyTestKey123"
    fp1 = fingerprint(key1)
    assert len(fp1) == 12
    assert fp1 == fingerprint(key1)
    assert fp1 != fingerprint("AIzaSyDifferentKey")
    assert fingerprint("") == ""


def test_empty_inputs_raise_value_error():
    with pytest.raises(ValueError, match="Cannot encrypt empty key"):
        encrypt_key("")
    with pytest.raises(ValueError, match="Cannot encrypt empty key"):
        encrypt_key("   ")
    with pytest.raises(ValueError, match="Cannot decrypt empty ciphertext"):
        decrypt_key("")
    with pytest.raises(ValueError, match="Cannot decrypt empty ciphertext"):
        decrypt_key("   ")


def test_validate_key_format_gemini():
    # Valid: AIza prefix, 39 chars
    valid_key = "AIzaSy" + "A" * 33
    assert len(valid_key) == 39
    assert validate_key_format("gemini", valid_key) is True

    # Invalid prefix
    assert validate_key_format("gemini", "BIzaSy" + "A" * 33) is False
    # Invalid length
    assert validate_key_format("gemini", "AIzaSyShort") is False
    assert validate_key_format("gemini", "AIzaSy" + "A" * 40) is False
    # Empty
    assert validate_key_format("gemini", "") is False


def test_unset_encryption_key_raises_in_non_test(monkeypatch):
    monkeypatch.delenv(ENV_VAR_ENCRYPTION_KEY, raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TESTING", "0")

    with pytest.raises(RuntimeError, match="FATAL: AI_KEYS_ENCRYPTION_KEY"):
        get_fernet_key()
