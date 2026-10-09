"""CRM data-access layer for the dashboard.

Pure SQLite persistence helpers for the ``jobs`` / ``applications`` tables.
No HTTP, cache, or process concerns live here, so the module is easy to test
and can be reused by the CLI/compiler paths.
"""

import os
import sqlite3
from datetime import datetime

import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)

#: Sentinel distinguishing "field omitted" from "explicitly cleared".
UNSET = object()

#: Status given to a job the moment it is first pushed to the CRM.
#: It only becomes "Applied" when the user confirms the application.
DEFAULT_NEW_STATUS = "Prepared"

TRACKER_COLUMNS = [
    "company", "position", "date_applied", "source", "job_url",
    "cv_pdf_path", "cover_pdf_path", "notes", "status", "updated_at",
]


def load_tracker_df() -> pd.DataFrame:
    """Load the CRM tracker view (applications joined to their job)."""
    db_path = os.path.join('data', 'karriere.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            q = '''
            SELECT j.company, j.title as position, a.applied_at as date_applied,
                   'AI Generated' as source, j.url as job_url,
                   a.cv_pdf_path, a.cover_pdf_path, a.notes, a.status as status, a.applied_at as updated_at
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            '''
            df = pd.read_sql_query(q, conn)
            conn.close()
            return df
        except Exception as e:
            logger.warning(f"Could not load from DB: {e}")
    return pd.DataFrame(columns=TRACKER_COLUMNS)


def clean_cell(v) -> str:
    """Normalize a DataFrame cell / scalar to a trimmed string."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def resolve_job_id(cursor, company: str, title: str, job_url: str = ""):
    """Resolve a job id prioritizing exact match, existing applications, and URL.

    When duplicate URLs or multiple job postings exist, prioritizes rows that
    already have an application record in CRM, followed by exact (company, title) match.
    """
    company = clean_cell(company)
    title = clean_cell(title)
    job_url = clean_cell(job_url)
    if job_url.lower() in ('nan', 'none', 'n/a', 'null', 'undefined', '#'):
        job_url = ''

    # 1. Exact match on (url, company, title)
    if job_url and company and title:
        cursor.execute(
            """
            SELECT j.id FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.url = ? AND j.company = ? AND j.title = ?
            ORDER BY (a.job_id IS NOT NULL) DESC, j.id DESC
            LIMIT 1
            """,
            (job_url, company, title)
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    # 2. Match by URL, prioritizing jobs with an existing application row in CRM
    if job_url:
        cursor.execute(
            """
            SELECT j.id FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.url = ?
            ORDER BY (a.job_id IS NOT NULL) DESC,
                     CASE WHEN j.company = ? AND j.title = ? THEN 3
                          WHEN j.company = ? THEN 2
                          WHEN j.title = ? THEN 1
                          ELSE 0 END DESC,
                     j.id DESC
            LIMIT 1
            """,
            (job_url, company, title, company, title)
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    # 3. Match by exact (company, title), prioritizing jobs with applications
    if company and title:
        cursor.execute(
            """
            SELECT j.id FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.company = ? AND j.title = ?
            ORDER BY (a.job_id IS NOT NULL) DESC, j.id DESC
            LIMIT 1
            """,
            (company, title)
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    # 4. Case-insensitive fallback on (company, title)
    if company and title:
        cursor.execute(
            """
            SELECT j.id FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE LOWER(TRIM(j.company)) = LOWER(TRIM(?)) AND LOWER(TRIM(j.title)) = LOWER(TRIM(?))
            ORDER BY (a.job_id IS NOT NULL) DESC, j.id DESC
            LIMIT 1
            """,
            (company, title)
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    return None


def upsert_tracker_row(company: str, position: str, job_url: str = "",
                       cv_path=UNSET, cover_path=UNSET, notes=UNSET,
                       status=UNSET, date_applied=UNSET, create: bool = True,
                       description=UNSET) -> bool:
    """Insert or update a SINGLE CRM application row.

    Only the addressed row is written, so a concurrent edit or deletion of a
    different application is never reverted (unlike writing a whole snapshot).
    The matched ``jobs`` row (and thus its company/title key and link) is never
    rewritten. Fields left as the ``UNSET`` sentinel keep their stored value;
    passing an explicit ``""`` clears the field (e.g. notes).

    A newly created CRM row starts as ``Prepared``. A ``description`` is stored
    on a newly created job and backfilled onto an existing job only when that
    job has no description yet; an existing description is never overwritten.

    A URL-only lookup (no company/title) is allowed when ``create=False``, and a
    missing database is initialized via ``setup_db`` when creating.
    """
    db_path = os.path.join('data', 'karriere.db')
    if not os.path.exists(db_path) and not create:
        return False

    company = clean_cell(company)
    position = clean_cell(position)
    job_url = clean_cell(job_url)
    if job_url.lower() in ('nan', 'none', 'n/a', 'null', 'undefined', '#'):
        job_url = ''
    if (not company or not position) and (create or not job_url):
        return False
    new_description = "" if description is UNSET else clean_cell(description)

    conn = None
    try:
        if not os.path.exists(db_path):
            from src.db.database import setup_db
            conn = setup_db(db_path)
        else:
            conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        # Resolve an existing row FIRST (URL, then exact key) so a differing
        # incoming spelling never creates a duplicate (company, title) key.
        job_id = resolve_job_id(cursor, company, position, job_url)
        if job_id is None and create:
            cursor.execute(
                'INSERT OR IGNORE INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)',
                (company, position, job_url, new_description)
            )
            job_id = resolve_job_id(cursor, company, position, job_url)
        if job_id is None:
            return False
        # Backfill a missing link on the resolved job row.
        if job_url:
            cursor.execute(
                "UPDATE jobs SET url = ? WHERE id = ? AND (url IS NULL OR url = '')",
                (job_url, job_id)
            )
        # Backfill a missing description; never overwrite a stored one.
        if new_description:
            cursor.execute(
                "UPDATE jobs SET description = ? WHERE id = ? AND (description IS NULL OR description = '')",
                (new_description, job_id)
            )

        cursor.execute(
            'SELECT cv_pdf_path, cover_pdf_path, notes, status, applied_at FROM applications WHERE job_id = ?',
            (job_id,)
        )
        existing = cursor.fetchone()
        if existing is None and not create:
            # Fallback: check if an application exists for any job with the same URL or company/title
            alt_row = None
            if job_url:
                cursor.execute(
                    """
                    SELECT a.job_id, a.cv_pdf_path, a.cover_pdf_path, a.notes, a.status, a.applied_at
                    FROM applications a
                    JOIN jobs j ON a.job_id = j.id
                    WHERE j.url = ?
                    LIMIT 1
                    """,
                    (job_url,)
                )
                alt_row = cursor.fetchone()
            if not alt_row and company and position:
                cursor.execute(
                    """
                    SELECT a.job_id, a.cv_pdf_path, a.cover_pdf_path, a.notes, a.status, a.applied_at
                    FROM applications a
                    JOIN jobs j ON a.job_id = j.id
                    WHERE LOWER(TRIM(j.company)) = LOWER(TRIM(?)) AND LOWER(TRIM(j.title)) = LOWER(TRIM(?))
                    LIMIT 1
                    """,
                    (company, position)
                )
                alt_row = cursor.fetchone()
            if alt_row:
                job_id = alt_row[0]
                existing = alt_row[1:]
            else:
                return False
        ex_cv, ex_cover, ex_notes, ex_status, ex_date = existing if existing else ('', '', '', None, '')

        # Paths: a non-empty value wins; empty/omitted keeps the stored value.
        final_cv = str(cv_path) if (cv_path is not UNSET and clean_cell(cv_path)) else (ex_cv or '')
        final_cover = str(cover_path) if (cover_path is not UNSET and clean_cell(cover_path)) else (ex_cover or '')
        # Notes: an explicit value wins, including "" to clear; omitted keeps stored.
        final_notes = (ex_notes or '') if notes is UNSET else str(notes if notes is not None else '')
        # Status: explicit non-empty wins; omitted keeps stored. A brand-new row
        # starts as "Prepared"; legacy rows with no stored status stay "Applied".
        fallback_status = DEFAULT_NEW_STATUS if existing is None else 'Applied'
        if status is UNSET:
            final_status = ex_status or fallback_status
        else:
            final_status = clean_cell(status) or ex_status or fallback_status
        # Applied date: explicit wins; omitted keeps stored; default today.
        if date_applied is UNSET or clean_cell(date_applied) == '':
            final_date = ex_date or datetime.now().strftime("%Y-%m-%d")
        else:
            final_date = str(date_applied)

        cursor.execute('''
        INSERT INTO applications (job_id, cv_pdf_path, cover_pdf_path, applied_at, notes, status)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            cv_pdf_path = excluded.cv_pdf_path,
            cover_pdf_path = excluded.cover_pdf_path,
            applied_at = excluded.applied_at,
            notes = excluded.notes,
            status = excluded.status
        ''', (job_id, final_cv, final_cover, final_date, final_notes, final_status))
        conn.commit()
        return True
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning(f"Failed saving CRM row: {e}")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def save_tracker_df(df: pd.DataFrame) -> None:
    """Bulk upsert of the rows in ``df`` (compatibility helper).

    Prefer ``upsert_tracker_row`` for single-row writes; this only touches the
    rows present in ``df`` and never rewrites unrelated applications.
    """
    for _, row in df.iterrows():
        upsert_tracker_row(
            company=clean_cell(row.get('company')),
            position=clean_cell(row.get('position')) or clean_cell(row.get('title')),
            job_url=clean_cell(row.get('job_url')),
            cv_path=clean_cell(row.get('cv_pdf_path')) or UNSET,
            cover_path=clean_cell(row.get('cover_pdf_path')) or UNSET,
            notes=(row.get('notes') if 'notes' in row and not pd.isna(row.get('notes')) else UNSET),
            status=clean_cell(row.get('status')) or UNSET,
            date_applied=clean_cell(row.get('date_applied')) or UNSET,
        )
