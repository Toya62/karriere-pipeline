#!/usr/bin/env python3
"""
scripts/rotate_ai_keys.py

Operator utility to rotate the Fernet encryption key used for user-provided API keys (BYOK).
Decrypts stored ciphertexts with the old key and re-encrypts with the new key in place.

Usage:
    python scripts/rotate_ai_keys.py --old-key <OLD_KEY> --new-key <NEW_KEY> [--dry-run]
Or set environment variables:
    export AI_KEYS_ENCRYPTION_KEY_OLD="old_fernet_key"
    export AI_KEYS_ENCRYPTION_KEY_NEW="new_fernet_key"
    python scripts/rotate_ai_keys.py
"""

import argparse
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cryptography.fernet import Fernet, InvalidToken
from src.core.key_vault import decrypt_key, encrypt_key
from src.db.database import get_db_connection


def rotate_keys(old_key: str, new_key: str, dry_run: bool = False, db_path: str = "data/karriere.db") -> dict:
    old_key_bytes = old_key.strip().encode("utf-8")
    new_key_bytes = new_key.strip().encode("utf-8")

    # Verify both keys are valid Fernet keys
    try:
        Fernet(old_key_bytes)
    except Exception as e:
        raise ValueError(f"Invalid old Fernet key: {e}")

    try:
        Fernet(new_key_bytes)
    except Exception as e:
        raise ValueError(f"Invalid new Fernet key: {e}")

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, user_id, provider, key_ciphertext, key_fingerprint FROM user_ai_keys")
    rows = cur.fetchall()

    print(f"Found {len(rows)} user AI key row(s) to process.")
    rotated_count = 0
    failed_count = 0

    updates = []
    for row in rows:
        key_id, user_id, provider, ciphertext, fp = row[0], row[1], row[2], row[3], row[4]
        try:
            plaintext = decrypt_key(ciphertext, key=old_key_bytes)
            new_ciphertext = encrypt_key(plaintext, key=new_key_bytes)
            updates.append((new_ciphertext, key_id))
            rotated_count += 1
            print(f"  ✓ User {user_id} [{provider}] (fp: {fp}) decrypted & re-encrypted.")
        except InvalidToken:
            print(f"  ✗ User {user_id} [{provider}] (fp: {fp}) failed: invalid token / wrong old key.")
            failed_count += 1
        except Exception as ex:
            print(f"  ✗ User {user_id} [{provider}] (fp: {fp}) error: {ex}")
            failed_count += 1

    if dry_run:
        print(f"\n[DRY RUN] Would update {rotated_count} key(s). No changes committed to database.")
    else:
        for new_cipher, kid in updates:
            cur.execute(
                "UPDATE user_ai_keys SET key_ciphertext = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_cipher, kid),
            )
        conn.commit()
        print(f"\n✓ Successfully rotated {rotated_count} key(s) in database. Failures: {failed_count}.")

    conn.close()
    return {"rotated": rotated_count, "failed": failed_count, "dry_run": dry_run}


def main():
    parser = argparse.ArgumentParser(description="Rotate BYOK Fernet encryption key.")
    parser.add_argument(
        "--old-key",
        default=os.environ.get("AI_KEYS_ENCRYPTION_KEY_OLD") or os.environ.get("AI_KEYS_ENCRYPTION_KEY"),
        help="Current/old Fernet key (or AI_KEYS_ENCRYPTION_KEY_OLD)",
    )
    parser.add_argument(
        "--new-key",
        default=os.environ.get("AI_KEYS_ENCRYPTION_KEY_NEW"),
        help="New Fernet key (or AI_KEYS_ENCRYPTION_KEY_NEW)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test decryption and re-encryption without writing to DB",
    )
    parser.add_argument(
        "--db-path",
        default="data/karriere.db",
        help="Path to SQLite DB (default data/karriere.db)",
    )

    args = parser.parse_args()

    if not args.old_key or not args.new_key:
        print("Error: Both --old-key and --new-key must be provided (or via env vars).")
        sys.exit(1)

    try:
        rotate_keys(args.old_key, args.new_key, dry_run=args.dry_run, db_path=args.db_path)
    except Exception as exc:
        print(f"Fatal error during key rotation: {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
