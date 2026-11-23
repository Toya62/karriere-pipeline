"""One-off data-quality cleanup for existing job rows (bug #9).

Applies the same normalisation the ingest path now performs to rows that
were stored before the fix:

* literal "nan" / "none" / "null" in company / title / location -> ""
* markdown escapes and formatting stripped from descriptions
  (``\\&`` -> ``&``, ``**bold**`` -> ``bold``, ...)
* duplicate skill variants collapsed (``C++`` / ``C/C++`` -> ``C++``) in
  ``user_jobs`` / ``evaluations`` ``matched_skills``
* the source-posting typo "Engineeer" -> "Engineer" in titles/descriptions
  (the typo comes from the source postings, not from our templates — no
  template fix applies)

Rows with an empty company or title after cleaning are REPORTED, not
deleted: deleting is destructive and needs a human decision.

Safety: dry-run by default (prints what would change, writes nothing).
``--apply`` writes the changes. ``--apply`` refuses a production ENV
unless ``--force`` is also passed. This script has never been run against
production data.

Usage (from the repo root):
    python scripts/cleanup_job_data_quality.py            # dry run, local SQLite
    python scripts/cleanup_job_data_quality.py --apply    # apply to local SQLite
    DATABASE_URL=... python scripts/cleanup_job_data_quality.py --apply --force
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.text_norm import (
    clean_text_block,
    clean_text_field,
    fix_known_typos,
    normalize_skills,
    strip_markdown,
)
from src.db.database import ENV, get_db_connection


def _clean_job(company, title, location, description):
    """Return (new_company, new_title, new_location, new_description, changes).

    ``changes`` lists which fields changed, for the report.
    """
    changes = []
    new_company = fix_known_typos(clean_text_field(company))
    if new_company != (company or ""):
        changes.append("company")
    new_title = fix_known_typos(clean_text_field(title))
    if new_title != (title or ""):
        changes.append("title")
    new_location = clean_text_field(location)
    if new_location != (location or ""):
        changes.append("location")
    new_desc = fix_known_typos(strip_markdown(clean_text_block(description)))
    if new_desc != (description or ""):
        changes.append("description")
    return new_company, new_title, new_location, new_desc, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/karriere.db",
                        help="SQLite path (default: data/karriere.db). "
                             "With DATABASE_URL set, the Postgres DB is used.")
    parser.add_argument("--apply", action="store_true",
                        help="Write the changes. Without it, dry-run only.")
    parser.add_argument("--force", action="store_true",
                        help="Allow --apply when ENV is production/prod.")
    args = parser.parse_args()

    if args.apply and ENV in ("production", "prod") and not args.force:
        print("REFUSED: --apply on a production ENV needs --force. "
              "Re-run with --force only after a backup.", file=sys.stderr)
        return 2

    conn = get_db_connection(args.db)
    cur = conn.cursor()
    stats = {
        "jobs_scanned": 0,
        "jobs_changed": 0,
        "company_fixed": 0,
        "title_fixed": 0,
        "location_fixed": 0,
        "description_fixed": 0,
        "empty_identity_reported": 0,
        "skills_scanned": 0,
        "skills_changed": 0,
    }
    try:
        cur.execute("SELECT id, company, title, location, COALESCE(description, '') FROM jobs ORDER BY id")
        for job_id, company, title, location, description in cur.fetchall():
            stats["jobs_scanned"] += 1
            new_company, new_title, new_location, new_desc, changes = _clean_job(
                company, title, location, description
            )
            if not new_company or not new_title:
                stats["empty_identity_reported"] += 1
                print(f"  job {job_id}: EMPTY company/title after cleaning "
                      f"(company={new_company!r} title={new_title!r}) — reported, not deleted")
            if not changes:
                continue
            stats["jobs_changed"] += 1
            for field in changes:
                stats[f"{field}_fixed"] += 1
            if args.apply:
                cur.execute(
                    "UPDATE jobs SET company = ?, title = ?, location = ?, description = ? WHERE id = ?",
                    (new_company, new_title, new_location, new_desc, job_id),
                )

        for table in ("user_jobs", "evaluations"):
            cur.execute(f"SELECT id, matched_skills FROM {table}")
            for row_id, skills in cur.fetchall():
                stats["skills_scanned"] += 1
                new_skills = normalize_skills(skills or "")
                if new_skills != (skills or ""):
                    stats["skills_changed"] += 1
                    if args.apply:
                        cur.execute(
                            f"UPDATE {table} SET matched_skills = ? WHERE id = ?",
                            (new_skills, row_id),
                        )

        if args.apply:
            conn.commit()
    finally:
        conn.close()

    print(f"Jobs scanned: {stats['jobs_scanned']}, changed: {stats['jobs_changed']} "
          f"(company {stats['company_fixed']}, title {stats['title_fixed']}, "
          f"location {stats['location_fixed']}, description {stats['description_fixed']})")
    print(f"Empty company/title rows reported (not deleted): {stats['empty_identity_reported']}")
    print(f"Skill lists scanned: {stats['skills_scanned']}, changed: {stats['skills_changed']}")
    if args.apply:
        print("APPLIED.")
    else:
        print("DRY RUN — no changes written. Re-run with --apply to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
