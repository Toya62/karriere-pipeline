"""
scripts/harvest_ats_slugs.py — Automated ATS Company Harvester & Prober.

Capabilities:
1. Passive Ingestion Hook: Extracts company slugs from incoming aggregator URLs
   (Personio, Ashby, Greenhouse, Recruitee) and appends to seed lists.
2. Active Database Prober: Takes unique company names from data/karriere.db,
   converts to candidate slugs, and concurrently probes Personio XML and Ashby JSON
   endpoints to discover active career portals.
"""

import os
import sys
import re
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.logger import get_logger
from src.core.utils import normalize_company_entity
from src.db.database import get_db_connection, DB_PATH

logger = get_logger("ats_harvester")

PERSONIO_SEED_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "scrapers", "seed_personio_companies.json"))
ASHBY_SEED_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "scrapers", "seed_ashby_companies.json"))

_BLOCKED_SLUGS = {
    "www", "app", "api", "support", "jobs", "careers", "career", "corp",
    "help", "status", "mail", "cdn", "staging", "dev", "test", "demo", "admin"
}


def extract_ats_slug_from_url(url: str) -> tuple[str, str] | None:
    """Extract (ats_type, slug) tuple from a direct ATS job URL."""
    if not url or not isinstance(url, str):
        return None

    # 1. Personio: https://{slug}.jobs.personio.(de|com)
    m_p = re.search(r"https?://([a-zA-Z0-9\-]+)\.jobs\.personio\.(?:de|com)", url, re.I)
    if m_p:
        slug = m_p.group(1).lower().strip()
        if slug and slug not in _BLOCKED_SLUGS:
            return ("personio", slug)

    # 2. Ashby: https://jobs.ashbyhq.com/{slug}
    m_a = re.search(r"https?://jobs\.ashbyhq\.com/([a-zA-Z0-9\-]+)", url, re.I)
    if m_a:
        slug = m_a.group(1).lower().strip()
        if slug and slug not in _BLOCKED_SLUGS:
            return ("ashby", slug)

    # 3. Greenhouse: https://boards.greenhouse.io/{slug} or job-boards.greenhouse.io/{slug}
    m_g = re.search(r"https?://(?:boards|job-boards)\.greenhouse\.io/([a-zA-Z0-9\-]+)", url, re.I)
    if m_g:
        slug = m_g.group(1).lower().strip()
        if slug and slug not in _BLOCKED_SLUGS:
            return ("greenhouse", slug)

    # 4. Recruitee: https://{slug}.recruitee.com
    m_r = re.search(r"https?://([a-zA-Z0-9\-]+)\.recruitee\.com", url, re.I)
    if m_r:
        slug = m_r.group(1).lower().strip()
        if slug and slug not in _BLOCKED_SLUGS:
            return ("recruitee", slug)

    return None


def append_slug_to_seed(ats_type: str, slug: str) -> bool:
    """Appends newly discovered slug to corresponding seed JSON file."""
    if not slug or slug in _BLOCKED_SLUGS:
        return False

    seed_path = None
    if ats_type == "personio":
        seed_path = PERSONIO_SEED_FILE
    elif ats_type == "ashby":
        seed_path = ASHBY_SEED_FILE

    if not seed_path:
        return False

    os.makedirs(os.path.dirname(seed_path), exist_ok=True)
    existing = set()
    if os.path.exists(seed_path):
        try:
            with open(seed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing = {s.strip().lower() for s in data if s.strip()}
        except Exception:
            existing = set()

    if slug in existing:
        return False

    existing.add(slug)
    try:
        with open(seed_path, "w", encoding="utf-8") as f:
            json.dump(sorted(existing), f, indent=2)
        logger.info(f"✨ Auto-discovered & saved new {ats_type.upper()} company: '{slug}'")
        return True
    except Exception as exc:
        logger.warning(f"Failed saving {slug} to {seed_path}: {exc}")
        return False


def probe_personio_slug(slug: str, timeout: int = 3) -> bool:
    """Check if company slug hosts an active Personio public XML feed."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/xml,application/xml",
    }
    for domain in ("jobs.personio.de", "jobs.personio.com"):
        url = f"https://{slug}.{domain}/xml"
        try:
            r = requests.get(url, headers=headers, impersonate="chrome120", timeout=timeout)
            if r.status_code == 200 and "<workzag-jobs>" in r.text:
                return True
        except Exception:
            pass
    return False


def probe_ashby_slug(slug: str, timeout: int = 3) -> bool:
    """Check if company slug hosts an active Ashby public JSON board."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(url, headers=headers, impersonate="chrome120", timeout=timeout)
        if r.status_code == 200 and "jobs" in r.json():
            return True
    except Exception:
        pass
    return False


def _generate_candidate_slugs(company_name: str) -> list[str]:
    """Generate candidate slug variations from a company name."""
    candidates = set()
    raw = company_name.lower().strip()
    raw = re.sub(r"\(.*?\)", "", raw)

    # 1. Normalized entity
    norm = normalize_company_entity(company_name).replace(" ", "-")
    if norm and len(norm) >= 3:
        candidates.add(norm)
        candidates.add(norm.replace("-", ""))

    # 2. Simple alphanumeric slug
    clean_s = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if clean_s and len(clean_s) >= 3:
        candidates.add(clean_s)
        candidates.add(clean_s.replace("-", ""))

    return [c for c in candidates if c not in _BLOCKED_SLUGS]


def probe_database_companies(db_path: str = DB_PATH, max_workers: int = 20) -> dict:
    """Read all company names from DB, generate slugs, and probe Personio + Ashby endpoints."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT company FROM jobs WHERE company IS NOT NULL AND company != ''")
    rows = cur.fetchall()
    conn.close()

    raw_companies = [r[0] for r in rows]
    logger.info(f"Loaded {len(raw_companies)} unique company names from {db_path} to probe.")

    slugs_to_test = set()
    for comp in raw_companies:
        for s in _generate_candidate_slugs(comp):
            slugs_to_test.add(s)

    logger.info(f"Generated {len(slugs_to_test)} candidate slugs to probe across Personio & Ashby.")

    new_personio = []
    new_ashby = []

    # Probe Personio
    logger.info("Probing Personio XML feeds...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        f_to_slug = {executor.submit(probe_personio_slug, s): s for s in slugs_to_test}
        for future in as_completed(f_to_slug):
            s = f_to_slug[future]
            try:
                if future.result():
                    if append_slug_to_seed("personio", s):
                        new_personio.append(s)
            except Exception:
                pass

    # Probe Ashby
    logger.info("Probing Ashby JSON feeds...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        f_to_slug = {executor.submit(probe_ashby_slug, s): s for s in slugs_to_test}
        for future in as_completed(f_to_slug):
            s = f_to_slug[future]
            try:
                if future.result():
                    if append_slug_to_seed("ashby", s):
                        new_ashby.append(s)
            except Exception:
                pass

    logger.info(f"Probe completed! Discovered {len(new_personio)} new Personio companies, {len(new_ashby)} new Ashby companies.")
    return {
        "new_personio": new_personio,
        "new_ashby": new_ashby
    }


def main():
    parser = argparse.ArgumentParser(description="Harvest and probe ATS company slugs")
    parser.add_argument("--probe-db", action="store_true", help="Probe company names from database")
    parser.add_argument("--db", default=DB_PATH, help="Path to database")
    parser.add_argument("--workers", type=int, default=20, help="Max parallel prober threads")
    args = parser.parse_args()

    if args.probe_db:
        probe_database_companies(db_path=args.db, max_workers=args.workers)
    else:
        logger.info("Use --probe-db to scan database companies against ATS endpoints.")


if __name__ == "__main__":
    main()

