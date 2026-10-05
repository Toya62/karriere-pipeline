"""Dismissals data-access layer for the dashboard.

Records manually dismissed jobs in SQLite (``evaluations``) and keeps the
durable ``data/crm_dismissals.json`` sync file in step. Pure persistence
logic — no HTTP concerns.
"""

import json
import os
import sqlite3
from datetime import datetime

import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)

DISMISS_COLUMNS = ["job_url", "company", "title", "gemini_status", "gemini_summary", "evaluated_at"]


def sync_dismissals_from_json(db_path: str = "data/karriere.db") -> int:
    """Synchronize committed data/crm_dismissals.json records into SQLite evaluations table."""
    dismiss_file = os.path.join('data', 'crm_dismissals.json')
    if not os.path.exists(dismiss_file) or not os.path.exists(db_path):
        return 0
    try:
        with open(dismiss_file, 'r', encoding='utf-8') as f:
            records = json.load(f)
        if not records:
            return 0
        from src.db.database import setup_db
        conn = setup_db(db_path)
        cursor = conn.cursor()
        synced = 0
        for r in records:
            u = str(r.get("job_url", "")).strip()
            c = str(r.get("company", "")).strip()
            p = str(r.get("position", "")).strip()
            job_id = None
            if u:
                cursor.execute("SELECT id FROM jobs WHERE url = ?", (u,))
                row = cursor.fetchone()
                if row:
                    job_id = row[0]
            if not job_id and c and p:
                cursor.execute("SELECT id FROM jobs WHERE company = ? AND title = ?", (c, p))
                row = cursor.fetchone()
                if row:
                    job_id = row[0]
            if not job_id and (c or p or u):
                c_name = c or "Unknown"
                t_name = p or (f"Dismissed ({u})" if u else f"Dismissed-{r.get('dismissed_at', '')}")
                cursor.execute("INSERT OR IGNORE INTO jobs (company, title, url) VALUES (?, ?, ?)", (c_name, t_name, u))
                if cursor.lastrowid:
                    job_id = cursor.lastrowid
                else:
                    cursor.execute("SELECT id FROM jobs WHERE company = ? AND title = ?", (c_name, t_name))
                    res = cursor.fetchone()
                    if res:
                        job_id = res[0]
            if job_id:
                cursor.execute("""
                INSERT INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
                VALUES (?, 'USER_DISMISSED', 0, 'NONE', '', '', '', 'Manually dismissed by user from dashboard.', ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = 'USER_DISMISSED',
                    summary = 'Manually dismissed by user from dashboard.'
                """, (job_id, r.get("dismissed_at", datetime.now().isoformat())))
                synced += 1
        conn.commit()
        conn.close()
        return synced
    except Exception as e:
        logger.warning(f"Failed to sync dismissals from JSON into SQLite: {e}")
        return 0


def load_dismissed_df() -> pd.DataFrame:
    """Load manually dismissed jobs from SQLite, synchronizing with crm_dismissals.json."""
    db_path = os.path.join('data', 'karriere.db')
    sync_dismissals_from_json(db_path)
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
            if not df.empty:
                return df
        except Exception as e:
            logger.warning(f"Could not load dismissed jobs from SQLite: {e}")

    # Fallback to durable JSON sync file
    dismiss_file = os.path.join('data', 'crm_dismissals.json')
    if os.path.exists(dismiss_file):
        try:
            with open(dismiss_file, 'r', encoding='utf-8') as f:
                records = json.load(f)
            if records:
                rows = []
                for r in records:
                    rows.append({
                        "job_url": r.get("job_url", ""),
                        "company": r.get("company", ""),
                        "title": r.get("position", ""),
                        "gemini_status": "USER_DISMISSED",
                        "gemini_summary": "Manually dismissed by user.",
                        "evaluated_at": r.get("dismissed_at", "")
                    })
                return pd.DataFrame(rows)
        except Exception as e:
            logger.warning(f"Could not load crm_dismissals.json: {e}")

    return pd.DataFrame(columns=DISMISS_COLUMNS)


def add_to_dismissed(job_url: str = None, company: str = None, position: str = None) -> None:
    """Permanently record a job as USER_DISMISSED in SQLite and crm_dismissals.json."""
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
            logger.info(f"Permanently marked job #{job_id} as USER_DISMISSED in SQLite")
        conn.close()

        # Durable Git synchronization file for dismissals
        dismiss_file = os.path.join('data', 'crm_dismissals.json')
        os.makedirs('data', exist_ok=True)
        dismissals = []
        if os.path.exists(dismiss_file):
            try:
                with open(dismiss_file, 'r', encoding='utf-8') as f:
                    dismissals = json.load(f)
            except Exception:
                dismissals = []

        dismissals.append({
            "company": company or "",
            "position": position or "",
            "job_url": job_url or "",
            "dismissed_at": datetime.now().isoformat()
        })
        seen_keys = set()
        deduped = []
        for d in dismissals:
            k = (d.get("company", "").strip().lower(), d.get("position", "").strip().lower(), d.get("job_url", "").strip())
            if k not in seen_keys:
                seen_keys.add(k)
                deduped.append(d)
        with open(dismiss_file, 'w', encoding='utf-8') as f:
            json.dump(deduped, f, indent=2)

    except Exception as e:
        logger.error(f"Failed to record dismissed job in SQLite: {e}")
        raise
