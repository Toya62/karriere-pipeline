"""Permanent scrape-time dedup against jobs the user already acted on.

A job that has a CRM application row (Prepared/Applied/Interview/...) or was
manually dismissed must never be re-saved or sent to AI scoring again, no
matter how long ago it was scraped. The time-windowed repost filters cannot
guarantee this, so this check has no date cutoff.
"""

import os
import sqlite3

import pandas as pd

from src.core.logger import get_logger
from src.core.utils import _normalize_company, _plain_url

logger = get_logger(__name__)


def _norm_title(value) -> str:
    return " ".join(str(value or "").lower().split())


def load_known_job_keys(db_path: str = "data/karriere.db") -> tuple[set[str], set[str]]:
    """Return (plain URLs, 'company|||title' keys) of applied/dismissed jobs."""
    urls: set[str] = set()
    keys: set[str] = set()
    if not db_path or not os.path.exists(db_path):
        return urls, keys
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        rows = conn.execute(
            """
            SELECT j.url, j.company, j.title FROM jobs j
            WHERE EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id)
               OR EXISTS (SELECT 1 FROM evaluations e
                          WHERE e.job_id = j.id AND e.status = 'USER_DISMISSED')
            """
        ).fetchall()
        for url, company, title in rows:
            clean = _plain_url(str(url or "")).strip()
            if clean:
                urls.add(clean)
            cn, tt = _normalize_company(str(company or "")), _norm_title(title)
            if cn and tt:
                keys.add(f"{cn}|||{tt}")
    except Exception as exc:
        logger.warning(f"Could not load applied/dismissed jobs for dedup: {exc}")
    finally:
        if conn is not None:
            conn.close()
    return urls, keys


def filter_known_jobs(df: pd.DataFrame, db_path: str = "data/karriere.db") -> pd.DataFrame:
    """Drop scraped rows that match an applied/dismissed job by URL or company+title."""
    before = len(df)
    if before == 0:
        return df
    urls, keys = load_known_job_keys(db_path)
    if not urls and not keys:
        return df

    def is_known(row) -> bool:
        url = _plain_url(str(row.get("job_url", "") or "")).strip()
        if url and url in urls:
            return True
        company = _normalize_company(str(row.get("company", "") or ""))
        title = _norm_title(row.get("title", row.get("position", "")))
        return bool(company and title and f"{company}|||{title}" in keys)

    mask = ~df.apply(is_known, axis=1)
    removed = int((~mask).sum())
    logger.info(f"  Known job (applied/dismissed): {before - removed:4d} / {before} kept  ({removed} removed)")
    return df[mask].reset_index(drop=True)
