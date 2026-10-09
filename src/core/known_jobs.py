"""Permanent scrape-time dedup against jobs the user already acted on.

A job that has a CRM application row (Prepared/Applied/Interview/...) or was
manually dismissed must never be re-saved or sent to AI scoring again, no
matter how long ago it was scraped. The time-windowed repost filters cannot
guarantee this, so this check has no date cutoff.
"""

import os
import re
import sqlite3
from typing import Any

import pandas as pd

from src.core.logger import get_logger
from src.core.utils import _plain_url

logger = get_logger(__name__)

GENDER_TAG_RE = re.compile(
    r"\s*[\(\[\{/\-]?\s*(?:m/w/d|m/f/d|w/m/d|d/m/w|mwd|mfd|wmd|gn|divers|all genders|m/w/div|geschlechtsneutral)\s*[\)\]\}]?",
    re.IGNORECASE,
)
COMPANY_LEGAL_RE = re.compile(
    r"\b(gmbh|ag|co|kg|se|inc|corp|ltd|s\.a\.|ug|haftungsbeschr\w*|holding|group|gruppe)\b",
    re.IGNORECASE,
)


def _norm_alphanumeric(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _clean_title(t: Any) -> str:
    if t is None or (isinstance(t, float) and pd.isna(t)):
        return ""
    cleaned = GENDER_TAG_RE.sub("", str(t))
    return _norm_alphanumeric(cleaned)


def _clean_company(c: Any) -> str:
    if c is None or (isinstance(c, float) and pd.isna(c)):
        return ""
    cleaned = COMPANY_LEGAL_RE.sub("", str(c))
    return _norm_alphanumeric(cleaned)


def _norm_title(value: Any) -> str:
    """Legacy helper for title normalization."""
    return _clean_title(value)


class KnownJobsIndex:
    """In-memory index supporting exact URL matching and fuzzy company+title overlap."""

    def __init__(self, urls: set[str], records: list[dict[str, str]]):
        self.urls: set[str] = urls
        self.records: list[dict[str, str]] = records

    def is_match(self, job_url: Any, company: Any, title: Any) -> bool:
        u_raw = "" if job_url is None or (isinstance(job_url, float) and pd.isna(job_url)) else str(job_url)
        clean_u = _plain_url(u_raw).strip().rstrip("/")
        if clean_u and clean_u in self.urls:
            return True

        c = _clean_company(company)
        t = _clean_title(title)
        if not c or not t:
            return False

        for rec in self.records:
            rc = rec["comp"]
            rt = rec["title"]
            if not rc or not rt:
                continue

            # Company match: exact equality or substring if >= 4 chars
            c_match = False
            if c == rc:
                c_match = True
            elif len(c) >= 4 and len(rc) >= 4 and (c in rc or rc in c):
                c_match = True

            if not c_match:
                continue

            # Title match: exact equality or substring if >= 6 chars
            t_match = False
            if t == rt:
                t_match = True
            elif len(t) >= 6 and len(rt) >= 6 and (t in rt or rt in t):
                t_match = True

            if c_match and t_match:
                return True

        return False


def load_known_job_keys(db_path: str = "data/karriere.db") -> tuple[set[str], set[str]]:
    """Return (plain URLs, 'company|||title' keys) of applied/dismissed jobs for backward compatibility."""
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
            clean = _plain_url(str(url or "")).strip().rstrip("/")
            if clean:
                urls.add(clean)
            cn, tt = _clean_company(company), _clean_title(title)
            if cn and tt:
                keys.add(f"{cn}|||{tt}")
    except Exception as exc:
        logger.warning(f"Could not load applied/dismissed jobs for dedup: {exc}")
    finally:
        if conn is not None:
            conn.close()
    return urls, keys


def load_known_jobs_index(db_path: str = "data/karriere.db") -> KnownJobsIndex:
    """Load an in-memory KnownJobsIndex with exact URLs and normalized company+title pairs."""
    urls: set[str] = set()
    records: list[dict[str, str]] = []
    if not db_path or not os.path.exists(db_path):
        return KnownJobsIndex(urls, records)
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
            clean = _plain_url(str(url or "")).strip().rstrip("/")
            if clean:
                urls.add(clean)
            c = _clean_company(company)
            t = _clean_title(title)
            if c and t:
                records.append({"comp": c, "title": t})
    except Exception as exc:
        logger.warning(f"Could not load applied/dismissed jobs for dedup: {exc}")
    finally:
        if conn is not None:
            conn.close()
    return KnownJobsIndex(urls, records)


def filter_known_jobs(df: pd.DataFrame, db_path: str = "data/karriere.db") -> pd.DataFrame:
    """Drop scraped rows that match an applied/dismissed job by URL or fuzzy company+title."""
    before = len(df)
    if before == 0:
        return df

    index = load_known_jobs_index(db_path)
    if not index.urls and not index.records:
        return df

    def is_known(row) -> bool:
        url = row.get("job_url", row.get("url", ""))
        company = row.get("company", "")
        title = row.get("title", row.get("position", ""))
        return index.is_match(url, company, title)

    mask = ~df.apply(is_known, axis=1)
    removed = int((~mask).sum())
    logger.info(f"  Known job (applied/dismissed): {before - removed:4d} / {before} kept  ({removed} removed)")
    return df[mask].reset_index(drop=True)

