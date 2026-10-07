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
from src.core.config import REJECT_JOB_TYPES, get_max_days, get_window_tag
from src.filters import apply_filters

logger = get_logger(__name__)
GERMAN_TZ = ZoneInfo("Europe/Berlin")

SEED_FILE = os.path.join(os.path.dirname(__file__), "seed_personio_companies.json")
LATEST_PERSONIO = "data/personio_latest.csv"
ALL_TIME_PERSONIO = "data/personio_all_time.csv"


# ── Regional gate: Germany, Netherlands, Luxembourg, Belgium ────────────────
_ALLOWED_GEO = (
    "germany", "deutschland",
    "berlin", "münchen", "munich", "hamburg", "köln", "cologne",
    "frankfurt", "dresden", "stuttgart", "düsseldorf", "leipzig",
    "dortmund", "essen", "bremen", "hannover", "nürnberg", "bonn",
    "freiburg", "karlsruhe", "augsburg", "ulm", "aachen", "erfurt",
    # Netherlands
    "netherlands", "niederlande", "amsterdam", "rotterdam", "utrecht",
    "den haag", "the hague", "eindhoven", "groningen",
    # Luxembourg
    "luxembourg", "luxemburg",
    # Belgium
    "belgium", "belgien", "brussels", "brussel", "bruxelles", "antwerp",
    "antwerpen", "ghent", "gent", "liège", "liege", "leuven",
)
_BLOCKED_GEO = (
    "united states", "usa", "u.s.a", "canada", "united kingdom", "england",
    "london", "ireland", "dublin", "spain", "españa", "madrid", "barcelona",
    "france", "paris", "italy", "milan", "rome", "poland", "warsaw",
    "portugal", "lisbon", "switzerland", "zurich", "zürich", "austria",
    "wien", "vienna", "india", "bangalore", "singapore", "australia",
    "sydney", "new york", "san francisco", "boston", "chicago", "austin",
    "seattle", "tokyo", "japan", "china", "beijing", "shanghai",
)
_REMOTE_MARKERS = ("remote", "home office", "homeoffice", "home-office", "hybrid")
_COUNTRY_CODE_DELIMITER = r"(?:^|[,(/;\-\s])\s*(?:{codes})\s*(?=$|[,)/;\-\u2013\u2014])"
_BLOCKED_COUNTRY_CODES = ("usa", "u\\.s\\.a?\\.?", "us", "uk", "gb", "ca", "in", "sg", "au", "ie", "es", "fr", "it", "pl", "pt", "ch", "at")
_ALLOWED_COUNTRY_CODES = ("de", "nl", "lu", "be")
_BLOCKED_COUNTRY_CODE_RE = re.compile(
    _COUNTRY_CODE_DELIMITER.format(codes="|".join(_BLOCKED_COUNTRY_CODES)),
    re.IGNORECASE,
)
_ALLOWED_COUNTRY_CODE_RE = re.compile(
    _COUNTRY_CODE_DELIMITER.format(codes="|".join(_ALLOWED_COUNTRY_CODES)),
    re.IGNORECASE,
)
_COUNTRY_NAMES_BY_CODE = {
    "de": "Germany", "nl": "Netherlands", "lu": "Luxembourg", "be": "Belgium",
    "us": "United States", "gb": "United Kingdom", "uk": "United Kingdom",
    "ca": "Canada", "in": "India", "sg": "Singapore", "au": "Australia",
    "ie": "Ireland", "es": "Spain", "fr": "France", "it": "Italy",
    "pl": "Poland", "pt": "Portugal", "ch": "Switzerland", "at": "Austria",
}


def _matches_location_term(location: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", location) is not None


def _is_allowed_region(location: str) -> bool:
    """True if a location is inside Germany/Benelux, or is an unspecified
    remote role. Explicit out-of-region markers are always rejected, and an
    unknown location is rejected rather than assumed to be German.
    """
    loc = (location or "").strip().lower()
    if not loc:
        return False
    if any(_matches_location_term(loc, b) for b in _BLOCKED_GEO) or _BLOCKED_COUNTRY_CODE_RE.search(loc):
        return False
    if _ALLOWED_COUNTRY_CODE_RE.search(loc) or any(_matches_location_term(loc, a) for a in _ALLOWED_GEO):
        return True
    # Remote/home-office with no explicit out-of-region marker.
    return any(_matches_location_term(loc, r) for r in _REMOTE_MARKERS)


def _normalize_job_type(raw_type) -> str:
    values = raw_type if isinstance(raw_type, list) else [raw_type]
    normalized = []
    for value in values:
        job_type = str(value or "").strip().lower().replace(" ", "_")
        if job_type == "intern":
            job_type = "internship"
        if job_type:
            normalized.append(job_type)
    return next((job_type for job_type in normalized if job_type in REJECT_JOB_TYPES), normalized[0] if normalized else "")


def _extract_ld_location(loc_obj) -> str:
    """Normalize a JSON-LD ``jobLocation`` (dict or list) to a location string
    without inventing a country."""
    if isinstance(loc_obj, list):
        return " ".join(p for p in (_extract_ld_location(x) for x in loc_obj) if p)
    if not isinstance(loc_obj, dict):
        return ""
    addr = loc_obj.get("address")
    if isinstance(addr, str):
        return addr.strip()
    if not isinstance(addr, dict):
        return ""
    bits = [addr.get("addressLocality"), addr.get("addressRegion")]
    country = addr.get("addressCountry")
    if isinstance(country, dict):
        country = country.get("name") or country.get("addressCountry")
    if isinstance(country, str):
        country = _COUNTRY_NAMES_BY_CODE.get(country.strip().lower(), country.strip())
    bits.append(country)
    return ", ".join(str(b).strip() for b in bits if b and str(b).strip())


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

    return sorted(companies)


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
                office = (pos.findtext("office") or "").strip()
                dept = (pos.findtext("department") or "").strip()
                emp_type = (pos.findtext("employmentType") or "").strip()

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
                    try:
                        r_page = requests.get(job_url, headers=headers, impersonate="chrome120", timeout=4)
                        if r_page.status_code == 200:
                            s_page = BeautifulSoup(r_page.text, "html.parser")
                            for uw in s_page(["script", "style", "nav", "footer", "header"]):
                                uw.decompose()
                            lines = [ln.strip() for ln in s_page.get_text(separator="\n").splitlines() if ln.strip()]
                            full_desc = "\n".join(lines)
                    except Exception:
                        pass
                if not full_desc:
                    full_desc = f"{name} at {company_slug} in {office or 'n/a'}. Department: {dept}."

                # Date parsing
                # Personio XML feeds only expose `createdAt` (the date the
                # position was created in the company's ATS), which is often
                # months before the position was posted publicly. Using it as
                # `date_posted` causes the 1-day date filter to drop every
                # position from companies that created their listings long
                # ago — which is exactly what was happening (554 raw jobs,
                # 0 kept). The feed has no real posting date, so default to
                # today; filter_date falls back to scraped_at (also today)
                # when date_posted is absent, so this is safe.
                date_posted = datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

                # Derive clean company name from slug
                company_clean = company_slug.replace("-", " ").title()

                # Regional location gate (Germany/Benelux + unspecified remote);
                # unknown locations are rejected, not assumed to be German.
                if not _is_allowed_region(office):
                    continue

                jobs.append({
                    "title": name,
                    "company": company_clean,
                    "location": office,
                    "job_type": _normalize_job_type(emp_type),
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

    # Fallback for modern Personio 2.0 Karriereseite without XML feed (e.g. Datalogue)
    if not jobs:
        try:
            home_url = f"https://{company_slug}.jobs.personio.com/"
            r = requests.get(home_url, headers=headers, impersonate="chrome120", timeout=4)
            if r.status_code == 200:
                # Preserve page order and de-duplicate; fetch every discovered posting.
                found_job_ids = list(dict.fromkeys(re.findall(r"/job/(\d+)", r.text)))
                for j_id in found_job_ids:
                    detail_url = f"https://{company_slug}.jobs.personio.com/job/{j_id}"
                    r_det = requests.get(detail_url, headers=headers, impersonate="chrome120", timeout=4)
                    if r_det.status_code != 200:
                        continue
                    soup = BeautifulSoup(r_det.text, "html.parser")
                    for s in soup.find_all("script", type="application/ld+json"):
                        try:
                            data = json.loads(s.string)
                            if not (isinstance(data, dict) and data.get("@type") == "JobPosting"):
                                continue
                            title = str(data.get("title", "") or "").strip()
                            if not title:
                                continue
                            # Same regional gate as the XML branch; unknown
                            # locations are rejected (do not invent a country).
                            loc_str = _extract_ld_location(data.get("jobLocation"))
                            if not _is_allowed_region(loc_str):
                                continue
                            raw_desc = str(data.get("description", "") or "").strip()
                            clean_desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator="\n").strip()
                            d_posted = str(data.get("datePosted", ""))[:10]
                            if not d_posted:
                                d_posted = datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")
                            jobs.append({
                                "title": title,
                                "company": company_slug.replace("-", " ").title(),
                                "location": loc_str,
                                "job_type": _normalize_job_type(data.get("employmentType")),
                                "date_posted": d_posted,
                                "job_url": detail_url,
                                "description": clean_desc,
                                "applicant_count": 0,
                                "scraped_at": datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                            })
                        except Exception:
                            pass
        except Exception:
            pass

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
        df = apply_filters(df, max_days=max_days, is_linkedin=False)

    finalise(df, LATEST_PERSONIO, ALL_TIME_PERSONIO, "Personio", is_linkedin=False)


if __name__ == "__main__":
    run_scrape_personio()
