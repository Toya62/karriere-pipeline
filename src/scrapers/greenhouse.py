"""
src/scrapers/greenhouse.py — High-Performance Greenhouse ATS Direct JSON Scraper

Directly queries public job-board API of top tech scaleups, unicorns, and engineering companies:
  https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

Features:
- Fast parallel ingestion via ThreadPoolExecutor & curl_cffi / requests
- High fidelity plain-text descriptions, departments, and 1-click apply links
- Regional gating: filters for Germany (Berlin, Munich, Hamburg, Essen, etc.) and European Remote
"""

import os
import sys
import re
import json
import html

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from curl_cffi import requests
from bs4 import BeautifulSoup

from src.core.logger import get_logger
from src.core.config import get_max_days, get_window_tag
from src.core.filters import apply_filters
from src.scrapers.personio import _is_allowed_region, _normalize_job_type

logger = get_logger(__name__)
GERMAN_TZ = ZoneInfo("Europe/Berlin")
SEED_FILE = os.path.join(os.path.dirname(__file__), "seed_greenhouse_companies.json")


def load_greenhouse_company_pool() -> list[str]:
    """Loads curated company slugs from Supabase ats_seeds table, seed file, and historical job URLs."""
    companies = set()

    # 1. Primary: Load active seeds from central database
    try:
        from src.db.database import get_active_ats_seeds
        db_seeds = get_active_ats_seeds("greenhouse")
        if db_seeds:
            companies.update(db_seeds)
    except Exception as e:
        logger.warning(f"Failed loading Greenhouse seeds from database: {e}")

    # 2. Secondary fallback: Load local seed file if present
    if os.path.exists(SEED_FILE):
        try:
            with open(SEED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                companies.update(c.strip().lower() for c in data if c.strip())
        except Exception as e:
            logger.warning(f"Failed loading {SEED_FILE}: {e}")

    # 3. Harvest from Database
    from src.db.database import get_db_connection, is_postgres
    db_path = "data/karriere.db"
    if is_postgres() or os.path.exists(db_path):
        try:
            conn = get_db_connection(db_path)
            c = conn.cursor()
            c.execute("SELECT url FROM jobs WHERE url LIKE '%greenhouse.io%'")
            for (url,) in c.fetchall():
                m = re.search(r"https?://(?:boards|job-boards)\.greenhouse\.io/([a-zA-Z0-9\-_]+)", str(url))
                if m:
                    sub = m.group(1).lower().strip()
                    if sub and sub not in ("embed", "api", "jobs", "v1"):
                        companies.add(sub)
            conn.close()
        except Exception:
            pass

    return sorted(companies)


def parse_greenhouse_job(job_data: dict, company_slug: str) -> dict | None:
    """Parses single Greenhouse job payload into standardized pipeline schema."""
    if not isinstance(job_data, dict):
        return None

    title = str(job_data.get("title", "")).strip()
    if not title:
        return None

    loc_obj = job_data.get("location")
    location = ""
    if isinstance(loc_obj, dict):
        location = str(loc_obj.get("name", "")).strip()
    elif isinstance(loc_obj, str):
        location = loc_obj.strip()

    loc_lower = location.lower()
    is_remote = "remote" in loc_lower or "anywhere" in loc_lower

    # Regional Gate (Germany / Benelux / Unspecified Remote)
    if not _is_allowed_region(location):
        if not is_remote:
            return None
        from src.scrapers.personio import _BLOCKED_GEO, _matches_location_term, _BLOCKED_COUNTRY_CODE_RE
        if any(_matches_location_term(loc_lower, b) for b in _BLOCKED_GEO) or bool(_BLOCKED_COUNTRY_CODE_RE.search(location)):
            return None

    # Apply URL
    job_url = str(job_data.get("absolute_url", "")).strip()
    if not job_url:
        job_id = job_data.get("id")
        job_url = f"https://job-boards.greenhouse.io/{company_slug}/jobs/{job_id}"

    # Description extraction: Greenhouse content is HTML-entity-escaped markup
    raw_content = str(job_data.get("content", "")).strip()
    if raw_content:
        # Unescape HTML entities (e.g. &lt;p&gt; -> <p>) before parsing markup
        unescaped = html.unescape(raw_content)
        description = BeautifulSoup(unescaped, "html.parser").get_text(separator="\n").strip()
        description = re.sub(r"\n{3,}", "\n\n", description)
    else:
        description = f"{title} at {company_slug.title()} in {location or 'Germany'}."

    # Date parsing: updated_at ISO format (e.g. 2026-11-06T15:20:00-04:00)
    updated_at = str(job_data.get("updated_at", "")).strip()
    date_posted = updated_at[:10] if updated_at else datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

    company_name = company_slug.replace("-", " ").title()

    return {
        "title": title,
        "company": company_name,
        "location": location or ("Remote" if is_remote else "Germany"),
        "job_type": "Full-time",
        "date_posted": date_posted,
        "job_url": job_url,
        "description": description,
        "applicant_count": 0,
        "scraped_at": datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_greenhouse_company(company_slug: str) -> list[dict]:
    """Fetches open positions for a single company via Greenhouse's public REST API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, impersonate="chrome120", timeout=8)
        if resp.status_code != 200:
            return []
        data = resp.json()
        raw_jobs = data.get("jobs", [])
        parsed = []
        for j in raw_jobs:
            item = parse_greenhouse_job(j, company_slug)
            if item:
                parsed.append(item)
        return parsed
    except Exception as e:
        logger.debug(f"Error scraping Greenhouse board {company_slug}: {e}")
        return []


def scrape_greenhouse(days: int | None = None) -> pd.DataFrame:
    """Entry point for Greenhouse ATS direct scraping."""
    max_days = days if days is not None else get_max_days()
    window_tag = f"{max_days}d" if max_days else get_window_tag()
    logger.info(f"Starting Greenhouse ATS scrape (window={window_tag}, max_days={max_days})...")

    companies = load_greenhouse_company_pool()
    logger.info(f"Found {len(companies)} Greenhouse companies to query in parallel...")

    all_jobs = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_greenhouse_company, slug): slug for slug in companies}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                all_jobs.extend(res)

    if not all_jobs:
        logger.warning("No jobs returned across all Greenhouse companies.")
        return pd.DataFrame()

    df = pd.DataFrame(all_jobs)
    initial_count = len(df)
    logger.info(f"Greenhouse raw extracted: {initial_count} jobs across {len(companies)} companies.")

    # Filter with candidate target search criteria
    df = apply_filters(df, max_days=max_days)
    filtered_count = len(df)
    logger.info(f"Greenhouse after profile & location filter: {filtered_count} matching jobs.")

    if not df.empty:
        from src.db.database import save_jobs_to_db
        saved = save_jobs_to_db(df, portal="greenhouse")
        logger.info(f"Saved {saved} jobs from Greenhouse into database.")

        os.makedirs("data", exist_ok=True)
        csv_path = f"data/greenhouse_{window_tag}.csv"
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved Greenhouse jobs to {csv_path}")

    return df


def run_scrape_greenhouse(days: int | None = None) -> pd.DataFrame:
    """Wrapper function conforming to pipeline scraper orchestrator standard."""
    return scrape_greenhouse(days=days)


if __name__ == "__main__":
    scrape_greenhouse(days=7)
