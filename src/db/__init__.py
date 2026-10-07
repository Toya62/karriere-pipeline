"""
src/db package
Provides SQLite database persistence, schema initialization, and
cross-run merging. Scrapers write directly to data/karriere.db via
save_jobs_to_db; no CSV ingestion layer exists.
"""

from src.db.database import (
    DB_PATH,
    merge_databases,
    normalize_scraped_at,
    save_jobs_to_db,
    setup_db,
    sync_remote_git_db,
)

__all__ = [
    "DB_PATH",
    "merge_databases",
    "normalize_scraped_at",
    "save_jobs_to_db",
    "setup_db",
    "sync_remote_git_db",
]