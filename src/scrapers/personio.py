"""
src/scrapers/personio.py — High-performance Personio XML ATS Scraper

Directly queries public XML feeds of German companies hosted on Personio:
  https://{company}.jobs.personio.de/xml  OR  https://{company}.jobs.personio.com/xml

Features:
- Fast concurrency via curl_cffi / ThreadPoolExecutor (under 5s for 100+ companies)
- Extracts structured position details, departments, office locations, clean text descriptions
- Auto-harvests newly discovered Personio companies from database & links
- Filters jobs through pipeline core rules (seniority, tech mismatch)
"""

import os
import re
import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import pandas as pd
from curl_cffi import requests

from src.core.logger import get_logger
from src.core.config import get_max_days, get_window_tag
from src.filters import apply_filters

logger = get_logger(__name__)
GERMAN_TZ = ZoneInfo("Europe/Berlin")

SEED_FILE = os.path.join(os.path.dirname(__file__), "seed_personio_companies.json")
LATEST_PERSONIO = "data/personio_latest.csv"
ALL_TIME_PERSONIO = "data/personio_all_time.csv"


def load_company_pool() -> list[str]:
    """Loads curated company list and discovers new ones from local SQLite database."""
    companies = set()

    # 1. Load seed file
    if os.path.exists(SEED_FILE):
        try:
            with open(SEED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                companies.update(c.strip().lower() for c in data if c.strip())
        except Exception as e:
            logger.warning(f"Failed loading {SEED_FILE}: {e}")

    # 2. Harvest from SQLite DB
    db_path = "data/karriere.db"
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT url FROM jobs WHERE url LIKE '%personio%'")
            for (url,) in c.fetchall():
                m = re.search(r"https?://([a-zA-Z0-9\-]+)\.jobs\.personio\.(?:de|com)", str(url))
                if m:
                    sub = m.group(1).lower().strip()
                    if sub and sub not in ("www", "app", "api", "support"):
                        companies.add(sub)
            conn.close()
        except Exception:
            pass

    return sorted(list(companies))


def fetch_company_xml(company_slug: str) -> list[dict]:
    """Fetches and parses a single company's Personio XML job feed."""
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8",
    }

    # Try .de then .com domain
    for domain in ("jobs.personio.de", "jobs.personio.com"):
        feed_url = f"https://{company_slug}.{domain}/xml"
        try:
            resp = requests.get(feed_url, headers=headers, impersonate="chrome120", timeout=4)
            if resp.status_code != 200 or "<workzag-jobs>" not in resp.text:
                continue

            root = ET.fromstring(resp.content)
            for pos in root.findall("position"):
                job_id = pos.findtext("id") or ""
                name = (pos.findtext("name") or "").strip()
                office = (pos.findtext("office") or "Germany").strip()
                dept = (pos.findtext("department") or "").strip()
                emp_type = (pos.findtext("employmentType") or "").strip()
                created_at = pos.findtext("createdAt") or ""

                if not name:
                    continue

                # Construct clean direct application / job URL
                job_url = f"https://{company_slug}.{domain}/job/{job_id}"

                # Extract and clean multi-part HTML descriptions
                desc_parts = []
                desc_el = pos.find("jobDescriptions")
                if desc_el is not None:
                    for jd in desc_el.findall("jobDescription"):
                        jd_name = (jd.findtext("name") or "").strip()
                        jd_val = (jd.findtext("value") or "").strip()
                        if jd_val:
                            soup = BeautifulSoup(jd_val, "html.parser")
                            clean_val = soup.get_text(separator="\n").strip()
                            clean_val = re.sub(r"\n{3,}", "\n\n", clean_val)
                            if jd_name:
                                desc_parts.append(f"### {jd_name}\n{clean_val}")
                            else:
                                desc_parts.append(clean_val)

                full_desc = "\n\n".join(desc_parts).strip()
                if not full_desc:
                    full_desc = f"{name} at {company_slug} in {office}. Department: {dept}."

                # Date parsing
                date_posted = ""
                if created_at:
                    try:
                        date_posted = str(created_at)[:10]
                    except Exception:
                        pass
                if not date_posted:
                    date_posted = datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

                # Derive clean company name from slug
                company_clean = company_slug.replace("-", " ").title()

                jobs.append({
                    "title": name,
                    "company": company_clean,
                    "location": office,
                    "date_posted": date_posted,
                    "job_url": job_url,
                    "description": full_desc,
                    "applicant_count": 0,
                    "scraped_at": datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                })
            # Break on first working domain
            if jobs:
                break
        except Exception:
            continue

    return jobs


def scrape_personio_network(max_workers: int = 15) -> pd.DataFrame:
    """Scrapes all configured Personio company feeds in parallel."""
    companies = load_company_pool()
    logger.info(f"Checking Personio XML feeds for {len(companies)} companies...")

    all_jobs = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_company_xml, c): c for c in companies}
        for future in as_completed(futures):
            c_slug = futures[future]
            try:
                company_jobs = future.result()
                if company_jobs:
                    logger.info(f"  ✓ {c_slug}: found {len(company_jobs)} position(s)")
                    all_jobs.extend(company_jobs)
            except Exception as e:
                logger.debug(f"  Error fetching {c_slug}: {e}")

    logger.info(f"Total raw Personio jobs collected: {len(all_jobs)}")
    return pd.DataFrame(all_jobs) if all_jobs else pd.DataFrame()


def run_scrape_personio() -> None:
    """Orchestrator runner for Personio scraper."""
    from src.scrapers.orchestrator import finalise

    max_days = get_max_days()
    window_tag = get_window_tag()

    logger.info("\n" + "=" * 46)
    logger.info("  Personio ATS Direct XML Scraper")
    logger.info(f"  Window : last {max_days} day(s) ({window_tag})")
    logger.info(f"  Output : {LATEST_PERSONIO} | {ALL_TIME_PERSONIO}")
    logger.info("=" * 46 + "\n")

    df = scrape_personio_network()
    if not df.empty:
        logger.info(f"\n  Raw Personio jobs before filtering: {len(df)}")
        df = apply_filters(df, is_linkedin=False)

    finalise(df, LATEST_PERSONIO, ALL_TIME_PERSONIO, "Personio", is_linkedin=False)


if __name__ == "__main__":
    run_scrape_personio()
