"""
src/scrapers/arbeitnow.py — Arbeitnow API Job Scraper for Germany

Pulls fresh tech, engineering, and remote jobs in Germany from Arbeitnow's public API:
  https://www.arbeitnow.com/api/job-board-api?page={n}

Features:
- Direct JSON REST API with 429 backoff retry
- Germany & DACH regional filtering via _is_allowed_region
- Dynamic pagination based on scraping window (max_days)
- HTML description cleanup via BeautifulSoup
- Unix timestamp conversion for accurate date_posted
- Early stop when items exceed cutoff date
- Pipeline core filters (seniority, CS relevance, noise, score)
"""

import re
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import pandas as pd

from src.core.logger import get_logger
from src.core.config import get_max_days, get_window_tag
from src.core.filters import apply_filters
from src.scrapers.personio import _is_allowed_region

logger = get_logger(__name__)
GERMAN_TZ = ZoneInfo("Europe/Berlin")


def fetch_arbeitnow_jobs(max_pages: int | None = None, max_days: int | None = None) -> pd.DataFrame:
    """Fetch jobs from Arbeitnow public REST API across multiple pages based on cutoff window."""
    if max_days is None:
        max_days = get_max_days()

    if max_pages is None:
        # Scale pages dynamically: ~3 pages per day of history, capped at 30
        max_pages = min(30, max(3, max_days * 3 + 2))

    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=max_days)).timestamp()

    all_jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    for page in range(1, max_pages + 1):
        url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
        logger.info(f"  Fetching Arbeitnow page {page}/{max_pages}...")

        resp = None
        for attempt in range(1, 4):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 429:
                    logger.warning(f"  Arbeitnow rate limited (429) on page {page}, sleeping {attempt * 2.5}s...")
                    time.sleep(attempt * 2.5)
                    continue
                break
            except Exception as e:
                logger.warning(f"  Attempt {attempt} failed on page {page}: {e}")
                time.sleep(1.5)

        if resp is None or resp.status_code != 200:
            logger.warning(f"  Arbeitnow page {page} returned HTTP {resp.status_code if resp else 'No response'}")
            break

        try:
            data = resp.json()
        except Exception as e:
            logger.warning(f"  Failed parsing JSON for page {page}: {e}")
            break

        items = data.get("data", [])
        if not items:
            logger.info(f"  No more jobs on Arbeitnow page {page}")
            break

        # Check if entire page is older than cutoff
        page_timestamps = [it.get("created_at", 0) for it in items if it.get("created_at")]
        if page_timestamps and all(ts < cutoff_ts for ts in page_timestamps):
            logger.info(f"  Reached date cutoff ({max_days}d) on page {page}. Stopping pagination.")
            break

        for item in items:
            ts = item.get("created_at", 0)
            if ts and ts < cutoff_ts:
                continue

            loc = str(item.get("location", "") or "").strip()
            is_remote = bool(item.get("remote", False))

            # Regional gate: Germany, German cities, or Remote with German context
            is_german_loc = _is_allowed_region(loc)
            is_german_remote = is_remote and any(
                g in loc.lower() for g in ("germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "")
            )
            if not (is_german_loc or is_german_remote):
                continue

            title = str(item.get("title", "") or "").strip()
            company = str(item.get("company_name", "") or "").strip()
            job_url = str(item.get("url", "") or "").strip()

            if not title or not company:
                continue

            # Clean HTML description
            raw_desc = item.get("description", "") or ""
            soup = BeautifulSoup(raw_desc, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            clean_desc = soup.get_text(separator="\n").strip()
            clean_desc = re.sub(r"\n{3,}", "\n\n", clean_desc)

            try:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(GERMAN_TZ)
                date_posted = dt.strftime("%Y-%m-%d")
            except Exception:
                date_posted = datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

            job_types = item.get("job_types", [])
            job_type_str = ", ".join(job_types) if isinstance(job_types, list) else str(job_types)

            all_jobs.append({
                "title": title,
                "company": company,
                "location": loc or ("Remote (Germany)" if is_remote else "Germany"),
                "job_url": job_url,
                "date_posted": date_posted,
                "description": clean_desc,
                "job_type": job_type_str,
                "applicant_count": 0,
                "scraped_at": datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            })

        # Polite delay to respect API rate limits
        time.sleep(0.8)

    logger.info(f"Total raw Arbeitnow jobs collected (Germany/DACH): {len(all_jobs)}")
    return pd.DataFrame(all_jobs) if all_jobs else pd.DataFrame()


def run_scrape_arbeitnow() -> None:
    """Orchestrator runner for Arbeitnow scraper."""
    from src.scrapers.orchestrator import finalise

    max_days = get_max_days()
    window_tag = get_window_tag()

    logger.info("\n" + "=" * 46)
    logger.info("  Arbeitnow Tech & Engineering Scraper")
    logger.info(f"  Window : last {max_days} day(s) ({window_tag})")
    logger.info("  Output : Supabase PostgreSQL")
    logger.info("=" * 46 + "\n")

    df = fetch_arbeitnow_jobs(max_days=max_days)
    if not df.empty:
        logger.info(f"\n  Raw Arbeitnow jobs before filtering: {len(df)}")
        df = apply_filters(df, max_days=max_days, is_linkedin=False)

    finalise(df, "Arbeitnow", is_linkedin=False)


if __name__ == "__main__":
    run_scrape_arbeitnow()
