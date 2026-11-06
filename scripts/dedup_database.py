"""
scripts/dedup_database.py — One-time & recurring database deduplication utility.

Groups jobs by canonical entity key:
  canonical_key = normalize_company_entity(company) + "|||" + normalize_title_entity(title)

For duplicate clusters:
1. Selects the canonical winning record:
   - Prefers direct ATS application URLs (Personio, Ashby, Greenhouse, Recruitee, Workday)
   - Prefers rich/longer descriptions
2. Migrates child evaluations and applications foreign keys to the winning job_id
3. Purges duplicate job rows
"""

import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse
from collections import defaultdict
from src.core.logger import get_logger
from src.core.utils import normalize_company_entity, normalize_title_entity
from src.db.database import get_db_connection, is_direct_ats_url, DB_PATH

logger = get_logger("dedup_database")


def deduplicate_database(db_path: str = DB_PATH, dry_run: bool = True) -> dict:
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, company, title, url, location, description, scraped_at FROM jobs ORDER BY id ASC")
    all_jobs = cur.fetchall()
    logger.info(f"Loaded {len(all_jobs)} total jobs from {db_path}")

    clusters = defaultdict(list)
    for row in all_jobs:
        j_id, company, title, url, location, desc, scraped_at = row
        ck = normalize_company_entity(company)
        tk = normalize_title_entity(title)
        if not ck or not tk or len(ck) < 2 or len(tk) < 2:
            continue
        key = f"{ck}|||{tk}"
        clusters[key].append({
            "id": j_id,
            "company": company,
            "title": title,
            "url": url or "",
            "location": location or "",
            "description": desc or "",
            "scraped_at": scraped_at or "",
            "is_ats": is_direct_ats_url(url or "")
        })

    dup_clusters = {k: v for k, v in clusters.items() if len(v) > 1}
    logger.info(f"Found {len(dup_clusters)} duplicate clusters across {sum(len(v) for v in dup_clusters.values())} rows.")

    merged_count = 0
    deleted_jobs = 0

    for key, jobs in dup_clusters.items():
        # Score jobs: +100 for ATS URL, +len(desc)/100, -id/1000000 (prefer earlier id on tie)
        def score_job(j):
            s = 0
            if j["is_ats"]:
                s += 1000
            s += min(len(j["description"]), 5000) / 10.0
            return s

        sorted_jobs = sorted(jobs, key=score_job, reverse=True)
        winner = sorted_jobs[0]
        losers = sorted_jobs[1:]

        logger.debug(f"Cluster: '{key}' -> Winner ID {winner['id']} ({winner['url'][:50]}), {len(losers)} losers")

        if not dry_run:
            winner_id = winner["id"]
            for loser in losers:
                loser_id = loser["id"]

                # 1. Handle evaluations
                cur.execute("SELECT id FROM evaluations WHERE job_id = ?", (winner_id,))
                winner_eval = cur.fetchone()
                cur.execute("SELECT id FROM evaluations WHERE job_id = ?", (loser_id,))
                loser_eval = cur.fetchone()

                if loser_eval and not winner_eval:
                    cur.execute("UPDATE evaluations SET job_id = ? WHERE job_id = ?", (winner_id, loser_id))
                elif loser_eval and winner_eval:
                    cur.execute("DELETE FROM evaluations WHERE job_id = ?", (loser_id,))

                # 2. Handle applications
                cur.execute("SELECT id FROM applications WHERE job_id = ?", (winner_id,))
                winner_app = cur.fetchone()
                cur.execute("SELECT id FROM applications WHERE job_id = ?", (loser_id,))
                loser_app = cur.fetchone()

                if loser_app and not winner_app:
                    cur.execute("UPDATE applications SET job_id = ? WHERE job_id = ?", (winner_id, loser_id))
                elif loser_app and winner_app:
                    cur.execute("DELETE FROM applications WHERE job_id = ?", (loser_id,))

                # 3. Delete loser job row
                cur.execute("DELETE FROM jobs WHERE id = ?", (loser_id,))
                deleted_jobs += 1

            # Ensure winner has best URL and description
            cur.execute("UPDATE jobs SET url = ?, description = ? WHERE id = ?", (winner["url"], winner["description"], winner["id"]))
            merged_count += 1

    if not dry_run:
        conn.commit()
        logger.info(f"Successfully merged {merged_count} clusters. Purged {deleted_jobs} duplicate job rows.")
    else:
        logger.info(f"[DRY-RUN] Would merge {len(dup_clusters)} clusters and purge {sum(len(v) - 1 for v in dup_clusters.values())} duplicate job rows.")

    conn.close()
    return {
        "clusters_found": len(dup_clusters),
        "duplicate_rows": sum(len(v) - 1 for v in dup_clusters.values()),
        "dry_run": dry_run
    }


def main():
    parser = argparse.ArgumentParser(description="Deduplicate database jobs by canonical entity key")
    parser.add_argument("--db", default=DB_PATH, help="Path to karriere database")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    deduplicate_database(db_path=args.db, dry_run=not args.apply)


if __name__ == "__main__":
    main()
