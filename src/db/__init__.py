"""
src/db package
Provides relational database persistence (Supabase PostgreSQL with SQLite fallback),
schema initialization, and cross-run deduplication. Scrapers write directly to
the database via save_jobs_to_db; no CSV ingestion layer exists.
"""

from src.db.database import (
    DB_PATH,
    is_direct_ats_url,
    merge_databases,
    normalize_scraped_at,
    save_jobs_to_db,
    setup_db,
    sync_remote_git_db,
)

__all__ = [
    "DB_PATH",
    "is_direct_ats_url",
    "merge_databases",
    "normalize_scraped_at",
    "save_jobs_to_db",
    "setup_db",
    "sync_remote_git_db",
]