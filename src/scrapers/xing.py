"""
scrapers/xing.py — XING Germany Job Scraper 
Extracts direct job listings from XING (xing.com/jobs) with JSON-LD structured data extraction.
"""

import os
import re
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import ALL_TIME_XING, WINDOW_TAG
from src.core.logger import get_logger

logger = get_logger(__name__)

GERMAN_TZ = ZoneInfo("Europe/Berlin")

XING_QUERIES = [
    "Data Engineer",
    "Python Developer",
    "Analytics Engineer",
    "Junior Data Engineer",
    "Cloud Engineer",
    "DevOps Engineer",
    "Software Integration Engineer",
    "Wissenschaftlicher Mitarbeiter Informatik",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def fetch_xing_job_detail(relative_or_full_url: str, max_days: int = 1) -> dict:
    """Fetches full job posting JSON-LD from a XING job URL. Returns {} if older than max_days."""
    url = relative_or_full_url if relative_or_full_url.startswith("http") else f"https://www.xing.com{relative_or_full_url}"
    clean_url = url.split("?")[0]
    try:
        resp = requests.get(clean_url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        ld_scripts = soup.find_all("script", type="application/ld+json")
        for s in ld_scripts:
            try:
                data = json.loads(s.string)
                # Handle single dict or list of objects
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        title = str(item.get("title", "") or "").strip()
                        comp = item.get("hiringOrganization", {})
                        company = comp.get("name", "") if isinstance(comp, dict) else str(comp)
                        
                        loc_obj = item.get("jobLocation", {})
                        location = ""
                        if isinstance(loc_obj, dict):
                            addr = loc_obj.get("address", {})
                            if isinstance(addr, dict):
                                location = addr.get("addressLocality") or addr.get("addressRegion") or ""
                            elif isinstance(addr, str):
                                location = addr

                        raw_desc = str(item.get("description", "") or "").strip()
                        soup_desc = BeautifulSoup(raw_desc, "html.parser")
                        desc_text = soup_desc.get_text(separator="\n").strip()
                        desc_text = re.sub(r"\n{3,}", "\n\n", desc_text)

                        date_posted = str(item.get("datePosted", "") or "")[:10]
                        if not date_posted:
                            date_posted = datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

                        # Early cutoff — skip old jobs before parsing description
                        try:
                            cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=max_days)).replace(
                                hour=0, minute=0, second=0, microsecond=0
                            )
                            job_dt = datetime.fromisoformat(date_posted).replace(tzinfo=timezone.utc)
                            if job_dt < cutoff:
                                return {}
                        except Exception:
                            pass

                        return {
                            "title": title,
                            "company": company,
                            "location": location,
                            "date_posted": date_posted,
                            "job_url": clean_url,
                            "description": desc_text,
                            "missing_keywords": "",
                            "applicant_count": None,
                            "scraped_at": datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                        }
            except Exception:
                pass
        return {}
    except Exception as e:
        logger.debug(f"[Xing] Failed fetching {clean_url}: {e}")
        return {}


def scrape_xing(queries: list[str] = None, max_pages: int = 2) -> pd.DataFrame:
    """Scrapes XING job search result pages and concurrently extracts full job data."""
    search_queries = queries or XING_QUERIES
    logger.info(f"🟢 Starting XING scrape across {len(search_queries)} queries...")

    seen_links = set()

    for q in search_queries:
        for page in range(1, max_pages + 1):
            url = f"https://www.xing.com/jobs/search?keywords={requests.utils.quote(q)}&location=Deutschland&page={page}&sort=date"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                found_on_page = 0
                for a in soup.find_all("a", href=True):
                    h = a["href"]
                    if re.match(r"^/jobs/[a-zA-Z0-9_-]+-\d+$", h):
                        clean_link = h.split("?")[0]
                        if clean_link not in seen_links:
                            seen_links.add(clean_link)
                            found_on_page += 1
                if found_on_page == 0:
                    break
            except Exception as e:
                logger.warning(f"[XING] Error fetching search page {page} for '{q}': {e}")
                break

    logger.info(f"🟢 Found {len(seen_links)} unique XING candidate jobs. Concurrently fetching JSON-LD details...")
    if not seen_links:
        return pd.DataFrame(columns=[
            "title", "company", "location", "date_posted", "job_url",
            "description", "missing_keywords", "applicant_count", "scraped_at"
        ])

    jobs = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        from src.config import get_max_days
        _max_days = get_max_days()
        future_map = {
            executor.submit(fetch_xing_job_detail, link, _max_days): link
            for link in seen_links
        }
        for future in as_completed(future_map):
            try:
                res = future.result()
                if res and res.get("title") and len(res.get("description", "")) > 50:
                    jobs.append(res)
            except Exception:
                pass

    df = pd.DataFrame(jobs)
    logger.info(f"✅ XING scraping completed: {len(df)} validated postings.")
    return df


def run_scrape_xing(window: str = None) -> pd.DataFrame:
    """Standard orchestrator runner for XING."""
    from src.filters import (
        filter_date, filter_seniority, filter_experience, filter_noise,
        filter_cs_relevance, filter_research_cs, filter_forbidden_tech,
        filter_language, filter_seen_reposts, filter_seen_reposts_by_url
    )
    from src.db.database import save_jobs_to_db

    df = scrape_xing()
    if df.empty:
        logger.info("[XING] No jobs found.")
        return df

    before = len(df)
    df = filter_date(df)
    df = filter_noise(df)
    df = filter_seniority(df)
    df = filter_cs_relevance(df)
    df = filter_forbidden_tech(df)
    df = filter_language(df)
    df = filter_seen_reposts(df)
    df = filter_seen_reposts_by_url(df)

    logger.info(f"🟢 XING Filter Pipeline: {len(df)} / {before} kept after dedup & filters.")
    if not df.empty:
        saved_cnt = save_jobs_to_db(df)
        logger.info(f"🟢 XING: Persisted {saved_cnt} fresh unique jobs to SQLite data/karriere.db")
    return df
