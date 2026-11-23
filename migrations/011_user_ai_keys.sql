-- Migration 011: User AI Keys for BYOK (Bring Your Own Key)
-- Stores encrypted user-provided API keys (v1: gemini)
-- Keys are encrypted at rest with AES-128-CBC + HMAC via Fernet

CREATE TABLE IF NOT EXISTS user_ai_keys (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL DEFAULT 'gemini',
    key_ciphertext  TEXT NOT NULL,
    key_fingerprint TEXT NOT NULL,
    key_last4       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    last_validated_at TIMESTAMP,
    last_error      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_user_ai_keys_user ON user_ai_keys(user_id);
