"""
src/scrapers/ashby.py — High-performance AshbyHQ ATS Direct JSON Scraper

Directly queries public job-board API of modern AI labs, tech scaleups, and engineering companies:
  https://api.ashbyhq.com/posting-api/job-board/{company_slug}

Features:
- Fast parallel ingestion via ThreadPoolExecutor & requests
- High fidelity plain-text descriptions, departments, and 1-click apply links
- Regional gating: filters for Germany, Benelux, and remote positions
"""

import os
import re
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from curl_cffi import requests

from src.core.logger import get_logger
from src.core.config import get_max_days, get_window_tag
from src.core.filters import apply_filters
from src.scrapers.personio import _is_allowed_region, _normalize_job_type

logger = get_logger(__name__)
GERMAN_TZ = ZoneInfo("Europe/Berlin")
SEED_FILE = os.path.join(os.path.dirname(__file__), "seed_ashby_companies.json")


def load_ashby_company_pool() -> list[str]:
    """Loads curated company slugs and harvests any newly discovered ones from database."""
    companies = set()

    # 1. Load seed file
    if os.path.exists(SEED_FILE):
        try:
            with open(SEED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                companies.update(c.strip().lower() for c in data if c.strip())
        except Exception as e:
            logger.warning(f"Failed loading {SEED_FILE}: {e}")

    # 2. Harvest from Database
    from src.db.database import get_db_connection, is_postgres
    db_path = "data/karriere.db"
    if is_postgres() or os.path.exists(db_path):
        try:
            conn = get_db_connection(db_path)
            c = conn.cursor()
            c.execute("SELECT url FROM jobs WHERE url LIKE '%ashbyhq%'")
            for (url,) in c.fetchall():
                m = re.search(r"https?://jobs\.ashbyhq\.com/([a-zA-Z0-9\-]+)", str(url))
                if m:
                    sub = m.group(1).lower().strip()
                    if sub and sub not in ("www", "app", "api", "support", "jobs"):
                        companies.add(sub)
            conn.close()
        except Exception:
            pass

    return sorted(companies)


def parse_ashby_job(job_data: dict, company_slug: str) -> dict | None:
    """Parses single Ashby job payload into standardized pipeline schema."""
    if not isinstance(job_data, dict):
        return None

    title = str(job_data.get("title", "")).strip()
    if not title:
        return None

    # Location & Remote resolution
    location = str(job_data.get("location", "")).strip()
    postal = job_data.get("address", {}).get("postalAddress", {})
    country = postal.get("addressCountry", "")
    locality = postal.get("addressLocality", "")

    full_loc_parts = [p for p in (location, locality, country) if p and p not in location]
    full_location = f"{location}, {', '.join(full_loc_parts)}" if full_loc_parts else location
    is_remote = bool(job_data.get("isRemote", False)) or str(job_data.get("workplaceType", "")).lower() in ("remote", "hybrid")

    # Regional Gate (Germany / Benelux / Unspecified Remote)
    if not _is_allowed_region(full_location):
        if not is_remote:
            return None
        # For remote roles, reject if explicitly US-only, UK-only, India-only
        from src.scrapers.personio import _BLOCKED_GEO, _matches_location_term
        loc_lower = full_location.lower()
        if any(_matches_location_term(loc_lower, b) for b in _BLOCKED_GEO):
            return None

    # URL preference: applyUrl opens the 1-click form, jobUrl opens position overview
    job_url = str(job_data.get("applyUrl") or job_data.get("jobUrl") or "").strip()
    if not job_url:
        job_url = f"https://jobs.ashbyhq.com/{company_slug}/{job_data.get('id', '')}"

    # Description extraction (Ashby provides clean descriptionPlain)
    description = str(job_data.get("descriptionPlain", "")).strip()
    if not description:
        raw_html = str(job_data.get("descriptionHtml", "")).strip()
        if raw_html:
            from bs4 import BeautifulSoup
            description = BeautifulSoup(raw_html, "html.parser").get_text(separator="\n").strip()

    dept = str(job_data.get("department", "")).strip()
    if not description:
        description = f"{title} at {company_slug.title()} in {location or 'Remote'}. Department: {dept}."

    # Date parsing
    pub_at = str(job_data.get("publishedAt", "")).strip()
    date_posted = pub_at[:10] if pub_at else datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

    company_name = company_slug.replace("-", " ").title()

    return {
        "title": title,
        "company": company_name,
        "location": location or ("Remote" if is_remote else "Germany"),
        "job_type": _normalize_job_type(job_data.get("employmentType", "FullTime")),
        "date_posted": date_posted,
        "job_url": job_url,
        "description": description,
        "applicant_count": 0,
        "scraped_at": datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_ashby_company(company_slug: str) -> list[dict]:
    """Fetches open positions for a single company via Ashby's public API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, impersonate="chrome120", timeout=5)
        if resp.status_code != 200:
            return []
        data = resp.json()
        raw_jobs = data.get("jobs", [])
        parsed_jobs = []
        for rj in raw_jobs:
            item = parse_ashby_job(rj, company_slug=company_slug)
            if item:
                parsed_jobs.append(item)
        return parsed_jobs
    except Exception as exc:
        logger.debug(f"Error fetching Ashby jobs for {company_slug}: {exc}")
        return []


def scrape_ashby_network(max_workers: int = 15) -> pd.DataFrame:
    """Scrapes all configured Ashby company boards in parallel."""
    companies = load_ashby_company_pool()
    logger.info(f"Checking Ashby API feeds for {len(companies)} tech companies...")

    all_jobs = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_ashby_company, c): c for c in companies}
        for future in as_completed(futures):
            c_slug = futures[future]
            try:
                company_jobs = future.result()
                if company_jobs:
                    logger.info(f"  ✓ {c_slug}: found {len(company_jobs)} position(s)")
                    all_jobs.extend(company_jobs)
            except Exception as e:
                logger.debug(f"  Error fetching {c_slug}: {e}")

    logger.info(f"Total raw Ashby jobs collected: {len(all_jobs)}")
    return pd.DataFrame(all_jobs) if all_jobs else pd.DataFrame()


def run_scrape_ashby() -> None:
    """Orchestrator runner for Ashby ATS scraper."""
    from src.scrapers.orchestrator import finalise

    max_days = get_max_days()
    window_tag = get_window_tag()

    logger.info("\n" + "=" * 46)
    logger.info("  AshbyHQ ATS Direct JSON API Scraper")
    logger.info(f"  Window : last {max_days} day(s) ({window_tag})")
    logger.info("  Output : data/karriere.db (direct SQLite)")
    logger.info("=" * 46 + "\n")

    df = scrape_ashby_network()
    if not df.empty:
        logger.info(f"\n  Raw Ashby jobs before filtering: {len(df)}")
        df = apply_filters(df, max_days=max_days, is_linkedin=False)

    finalise(df, "Ashby", is_linkedin=False)


if __name__ == "__main__":
    run_scrape_ashby()
