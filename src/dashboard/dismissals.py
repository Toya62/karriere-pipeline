"""Dismissals data-access layer for the dashboard.

Dismissed jobs live only in SQLite (``evaluations.status = 'USER_DISMISSED'``).
There is no JSON sync file: nothing is read from or written to git.
Pure persistence logic — no HTTP concerns.
"""

import os
import sqlite3

import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)

DISMISS_COLUMNS = ["job_url", "company", "title", "gemini_status", "gemini_summary", "evaluated_at"]


def sync_dismissals_from_json(db_path: str = "data/karriere.db") -> int:
    """Deprecated no-op kept for import compatibility.

    Dismissals are DB-only now, so there is nothing to synchronize and a stale
    ``data/crm_dismissals.json`` can no longer re-hide jobs.
    """
    return 0


def load_dismissed_df() -> pd.DataFrame:
    """Load manually dismissed jobs from SQLite."""
    db_path = os.path.join('data', 'karriere.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            q = '''
            SELECT j.url as job_url, j.company, j.title, e.status as gemini_status, e.summary as gemini_summary, e.evaluated_at
            FROM evaluations e
            JOIN jobs j ON e.job_id = j.id
            WHERE e.status = 'USER_DISMISSED'
            '''
            df = pd.read_sql_query(q, conn)
            conn.close()
            return df
        except Exception as e:
            logger.warning(f"Could not load dismissed jobs from SQLite: {e}")

    return pd.DataFrame(columns=DISMISS_COLUMNS)


def add_to_dismissed(job_url: str = None, company: str = None, position: str = None) -> None:
    """Record a job as USER_DISMISSED in SQLite only."""
    from datetime import datetime
    from src.db.database import setup_db
    try:
        db_path = os.path.join('data', 'karriere.db')
        conn = setup_db(db_path)
        cursor = conn.cursor()

        job_id = None
        if job_url:
            cursor.execute("SELECT id FROM jobs WHERE url = ?", (job_url,))
            row = cursor.fetchone()
            if row:
                job_id = row[0]
        if not job_id and company and position:
            cursor.execute("SELECT id FROM jobs WHERE company = ? AND title = ?", (company, position))
            row = cursor.fetchone()
            if row:
                job_id = row[0]

        if not job_id and (company or position or job_url):
            c_name = str(company or "Unknown").strip()
            if not position:
                t_name = f"Dismissed ({job_url})" if job_url else f"Dismissed-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            else:
                t_name = str(position).strip()

            cursor.execute(
                "INSERT OR IGNORE INTO jobs (company, title, url) VALUES (?, ?, ?)",
                (c_name, t_name, job_url or "")
            )
            if cursor.lastrowid:
                job_id = cursor.lastrowid
            else:
                cursor.execute("SELECT id FROM jobs WHERE company = ? AND title = ?", (c_name, t_name))
                row = cursor.fetchone()
                if row:
                    job_id = row[0]

        if job_id:
            cursor.execute('''
            INSERT INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
            VALUES (?, 'USER_DISMISSED', 0, 'NONE', '', '', '', 'Manually dismissed by user from dashboard.', datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
                status = 'USER_DISMISSED',
                summary = 'Manually dismissed by user from dashboard.',
                evaluated_at = datetime('now')
            ''', (job_id,))
            conn.commit()
            logger.info(f"Marked job #{job_id} as USER_DISMISSED in SQLite")
        conn.close()
    except Exception as e:
        logger.error(f"Failed to record dismissed job in SQLite: {e}")
        raise
