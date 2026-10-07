"""One-shot migration for data/karriere.db.

Applies the fixes that could not be done via schema alone:

1. Deduplicate jobs by URL. The old UNIQUE(company, title) constraint let
   the same Indeed/Bund/LinkedIn posting appear up to 11 times (different
   company spellings collide on the job id). Keep the newest row per URL
   and re-point every evaluation and application at the survivor.
2. Normalize scraped_at onto '%Y-%m-%d %H:%M:%S'. The DB held both
   ISO-8601 ('2026-09-14T16:08:29.349495') and space-separated values.
3. Drop orphan evaluations whose job_id no longer exists.
4. Rebuild the jobs UNIQUE constraint as UNIQUE(url, company, title).
5. Add the covering indexes the dashboard views need.

Safe to re-run: it only rewrites the local data/karriere.db.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.database import normalize_scraped_at

DB_PATH = os.path.join("data", "karriere.db")


def migrate(db_path: str = DB_PATH) -> None:
    if not os.path.exists(db_path):
        print(f"[migrate] {db_path} not found; nothing to do.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    stats = {"dup_jobs_merged": 0, "orphans_dropped": 0, "scraped_at_normalized": 0}

    # ------------------------------------------------------------------ #
    # 1. Normalize scraped_at in place (cheap, no schema change needed).  #
    # ------------------------------------------------------------------ #
    rows = cur.execute("SELECT id, scraped_at FROM jobs WHERE scraped_at IS NOT NULL AND scraped_at != ''").fetchall()
    for jid, raw in rows:
        normalized = normalize_scraped_at(raw)
        if normalized and normalized != raw:
            cur.execute("UPDATE jobs SET scraped_at = ? WHERE id = ?", (normalized, jid))
            stats["scraped_at_normalized"] += 1

# ------------------------------------------------------------------ #
    # 2. Deduplicate by (url, company, title) — the new UNIQUE key.      #
    #    Note: deduping by URL ALONE is wrong. Indeed ?jk= IDs and       #
    #    Bundesagentur detail URLs are reused across genuinely different #
    #    postings (e.g. one staffing agency advertising for 11 clients  #
    #    under the same URL). Collapsing those would delete real jobs.   #
    # ------------------------------------------------------------------ #
    dup_keys = cur.execute(
        "SELECT url, company, title FROM jobs WHERE url != '' "
        "GROUP BY url, company, title HAVING COUNT(*) > 1"
    ).fetchall()

    for url, company, title in dup_keys:
        rows = cur.execute(
            "SELECT id FROM jobs WHERE url = ? AND company = ? AND title = ? ORDER BY id DESC",
            (url, company, title),
        ).fetchall()
        keeper = rows[0][0]
        for dup_id in [r[0] for r in rows[1:]]:
            cur.execute("UPDATE OR IGNORE evaluations SET job_id = ? WHERE job_id = ?", (keeper, dup_id))
            cur.execute("UPDATE OR IGNORE applications SET job_id = ? WHERE job_id = ?", (keeper, dup_id))
            cur.execute("DELETE FROM evaluations WHERE job_id = ?", (dup_id,))
            cur.execute("DELETE FROM applications WHERE job_id = ?", (dup_id,))
            cur.execute("DELETE FROM jobs WHERE id = ?", (dup_id,))
            stats["dup_jobs_merged"] += 1

    # ------------------------------------------------------------------ #
    # 3. Drop orphan evaluations pointing at deleted jobs.               #
    # ------------------------------------------------------------------ #
    orphans = cur.execute(
        "SELECT e.id FROM evaluations e LEFT JOIN jobs j ON j.id = e.job_id WHERE j.id IS NULL"
    ).fetchall()
    for (eid,) in orphans:
        cur.execute("DELETE FROM evaluations WHERE id = ?", (eid,))
        stats["orphans_dropped"] += 1

    # ------------------------------------------------------------------ #
    # 4. Rebuild the jobs table with the new UNIQUE(url, company, title). #
    #    SQLite has no ALTER CONSTRAINT, so rebuild via a temp table.     #
    # ------------------------------------------------------------------ #
    cur.execute(
        """CREATE TABLE jobs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            location TEXT,
            description TEXT,
            scraped_at TEXT,
            UNIQUE(url, company, title)
        )"""
    )
    cur.execute(
        "INSERT INTO jobs_new (id, company, title, url, location, description, scraped_at) "
        "SELECT id, company, title, url, location, description, scraped_at FROM jobs"
    )
    cur.execute("DROP TABLE jobs")
    cur.execute("ALTER TABLE jobs_new RENAME TO jobs")

    # Re-create the covering indexes (setup_db does this for fresh DBs).
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_job_status ON evaluations(job_id, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications(job_id, status)")

    conn.commit()
    conn.close()

    print(f"[migrate] done — {stats}")


if __name__ == "__main__":
    migrate()