# scraper.py  —  Pipeline core orchestrator

import os
import time
from datetime import datetime, timezone
import pandas as pd

from src.config import (
    BOOLEAN_QUERIES, LINKEDIN_RESULTS_WANTED, MAX_APPLICANTS,
    LATEST_LINKEDIN, ALL_TIME_LINKEDIN, LATEST_INDEED, ALL_TIME_INDEED,
    BA_BROAD_QUERIES, BA_MAX_RESULTS, LATEST_BA, ALL_TIME_BA,
    OUTPUT_COLS, ALL_TIME_COMBINED
)
from src.config import get_indeed_hours_old, get_linkedin_hours_old, get_window_tag
from src.filters import (
    apply_filters, filter_noise, filter_reposts, filter_seen_reposts,
    filter_seen_reposts_by_url, filter_against_existing_catalog, RESEARCH_ROLE_PAT
)
from src.db.file_io import _save_csv, dedup, update_all_time, purge_empty_desc_from_all_time
from src.core.utils import _clean_desc, _plain_url, _has_desc
from src.core.logger import get_logger
logger = get_logger(__name__)

_ALL_TIME_FILES = [
    "data/ba_all_time.csv",
    "data/linkedin_all_time.csv",
    "data/indeed_all_time.csv",
    "data/stepstone_all_time.csv",
    "data/bund_all_time.csv",
    "data/xing_all_time.csv",
]


def _compute_score(v) -> int:
    """Compute date freshness score (0 to 50, fallback 0 for missing/invalid)."""
    s = str(v).strip() if v is not None else ""
    if not s or s.lower() in ("nan", "none", "nat", "", "invalid"):
        return 0
    try:
        dt = pd.to_datetime(s, utc=True, errors="coerce")
        if pd.isna(dt):
            return 0
        now = datetime.now(tz=timezone.utc)
        age_hours = (now - dt).total_seconds() / 3600.0
        if age_hours < 24:
            return max(0, min(50, int(50 - age_hours)))
        return 0
    except Exception:
        return 0



def save_jobs_to_db(df: pd.DataFrame) -> int:
    """Save scraped jobs directly into SQLite database data/karriere.db."""
    if df is None or df.empty:
        return 0
    import sqlite3
    db_path = os.path.join("data", "karriere.db")
    if not os.path.exists("data"):
        os.makedirs("data", exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT,
        title TEXT,
        url TEXT,
        location TEXT,
        description TEXT,
        scraped_at TIMESTAMP,
        UNIQUE(company, title)
    )''')
    
    saved = 0
    for _, r in df.iterrows():
        c = str(r.get("company", "")).strip()
        t = str(r.get("title", "")).strip()
        if not c or not t:
            continue
        u = str(r.get("job_url", r.get("link", ""))).strip()
        loc = str(r.get("location", "")).strip()
        desc = str(r.get("description", "")).strip()
        if desc == "nan": desc = ""
        scraped = str(r.get("scraped_at", r.get("date_posted", ""))).strip()
        
        cursor.execute('''
        INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (c, t, u, loc, desc, scraped))
        
        if desc:
            cursor.execute('''
            UPDATE jobs SET description = ? 
            WHERE company = ? AND title = ? AND (description IS NULL OR description = '' OR length(description) < 50)
            ''', (desc, c, t))
            
        if u and not u.startswith("mailto:"):
            cursor.execute('''
            UPDATE jobs SET url = ? 
            WHERE company = ? AND title = ? AND (url IS NULL OR url = '' OR url LIKE 'mailto:%')
            ''', (u, c, t))
            
        saved += 1
        
    conn.commit()
    conn.close()
    return saved


def finalise(
    df: pd.DataFrame,
    latest_file: str,
    all_time_file: str,
    label: str,
    drop_cols: set | None = None,
    is_linkedin: bool = False,
) -> None:
    if df.empty:
        logger.info(f"  {label}: no jobs to save.")
        return

    df = dedup(df)
    df = filter_noise(df)

    if df.empty:
        logger.info(f"  {label}: all jobs filtered by noise gate.")
        return

    if drop_cols:
        df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    for col in [c for c in df.columns if c.startswith("_")]:
        df = df.drop(columns=[col])

    for col in ("site_name", "applicant_count", "is_remote", "num_applicants",
                "applicants", "listing_type", "is_reposted"):
        if col in df.columns:
            df = df.drop(columns=[col])

    if "description" in df.columns:
        df["description"] = df["description"].apply(
            lambda v: _clean_desc(str(v)) if v and str(v).strip() else ""
        )

    try:
        df["date_posted"] = pd.to_datetime(df["date_posted"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    from src.core.utils import get_german_timestamp_str
    now_stamp = get_german_timestamp_str()
    if "scraped_at" not in df.columns or df["scraped_at"].isna().all():
        df["scraped_at"] = now_stamp
    else:
        df["scraped_at"] = df["scraped_at"].fillna(now_stamp).replace("", now_stamp)

    # Post-processing
    df = filter_reposts(df)
    df = filter_seen_reposts_by_url(df)
    df = filter_seen_reposts(df)
    df = filter_against_existing_catalog(df)

    if "date_posted" in df.columns:
        df = df.sort_values("date_posted", ascending=False, na_position="last").reset_index(drop=True)

    # Filter out low-scoring / under-scored jobs (score < 20) to save space and clean up dataset
    if "score" in df.columns:
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
        df = df[df["score"] >= 20].reset_index(drop=True)

    for col in OUTPUT_COLS:
        if col not in df.columns:
            df[col] = ""
    df = df[OUTPUT_COLS]

    try:
        saved_cnt = save_jobs_to_db(df)
        logger.info(f"  {label}: Persisted {saved_cnt} fresh unique jobs directly into data/karriere.db")
    except Exception as db_err:
        logger.warning(f"Could not persist scraped jobs directly to SQLite: {db_err}")

    no_desc_count = (df["description"].fillna("").str.strip() == "").sum()
    logger.info(f"\n  {label}: {len(df)} jobs processed.")
    if no_desc_count:
        logger.info(f"  {no_desc_count} job(s) have no description")
    logger.info("")

    for _, r in df.iterrows():
        is_res   = bool(RESEARCH_ROLE_PAT.search(str(r.get("title", ""))))
        tag      = " [R]" if is_res else ""
        has_d    = _has_desc(str(r.get("description", "")))
        desc_tag = "" if has_d else "  [no desc - open link]"
        logger.info(f"  * {str(r['title'])[:55]}{tag}{desc_tag}")
        logger.info(f"    {str(r['company'])[:40]} | {str(r['location'])[:35]}")
        logger.info(f"    {_plain_url(str(r.get('job_url', ''))[:110])}")
        logger.info("")

    update_all_time(df, all_time_file)


def run_scrape_linkedin():
    linkedin_hours_old = get_linkedin_hours_old()
    logger.info("\n" + "=" * 46)
    logger.info("  LinkedIn Fast Scraper (Two-Phase)")
    logger.info(f"  Window : last 24h (LinkedIn always 24h)")
    logger.info(f"  Queries: {len(BOOLEAN_QUERIES)} high-yield boolean terms")
    logger.info(f"  Output : {LATEST_LINKEDIN}  |  {ALL_TIME_LINKEDIN}")
    logger.info(f"  Applicant cap: < {MAX_APPLICANTS}")
    logger.info("=" * 46 + "\n")

    from src.scrapers.linkedin import scrape_linkedin, hydrate_linkedin_jobs

    li_frames = []
    for query in BOOLEAN_QUERIES:
        try:
            jobs = scrape_linkedin(query, results_wanted=LINKEDIN_RESULTS_WANTED, hours_old=linkedin_hours_old)
            count = 0 if jobs is None or jobs.empty else len(jobs)
            if count:
                li_frames.append(jobs)
            logger.info(f"  '{query[:40]}...': {count} rows (metadata)")
        except Exception as exc:
            logger.info(f"  Warning: '{query[:40]}...' failed: {exc}")
        time.sleep(1)

    li_df = pd.concat(li_frames, ignore_index=True) if li_frames else pd.DataFrame()
    if not li_df.empty:
        logger.info(f"\n  Raw LinkedIn jobs: {len(li_df)}")
        li_df = dedup(li_df)
        li_df = filter_against_existing_catalog(li_df)
        li_df = hydrate_linkedin_jobs(li_df, max_workers=8)
        li_df = apply_filters(li_df, is_linkedin=True)

    finalise(li_df, LATEST_LINKEDIN, ALL_TIME_LINKEDIN, "LinkedIn", is_linkedin=True)


def run_scrape_indeed():
    from src.config import INDEED_RESULTS_WANTED
    indeed_hours_old = get_indeed_hours_old()
    logger.info("\n" + "=" * 46)
    logger.info("  Indeed Germany Scraper")
    logger.info(f"  Window : last {indeed_hours_old}h")
    logger.info(f"  Queries: {len(BOOLEAN_QUERIES)} boolean terms")
    logger.info(f"  Output : {LATEST_INDEED}  |  {ALL_TIME_INDEED}")
    logger.info("=" * 46 + "\n")

    from src.scrapers.indeed import scrape_indeed

    frames = []
    for query in BOOLEAN_QUERIES:
        try:
            jobs = scrape_indeed(query, results_wanted=INDEED_RESULTS_WANTED, hours_old=indeed_hours_old)
            count = 0 if jobs is None or jobs.empty else len(jobs)
            if count:
                frames.append(jobs)
            logger.info(f"  '{query[:40]}...': {count} rows")
        except Exception as exc:
            logger.info(f"  Warning: '{query[:40]}...' failed: {exc}")
        time.sleep(2)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not df.empty:
        logger.info(f"\n  Raw Indeed jobs: {len(df)}")
        df = apply_filters(df, is_linkedin=False)

    finalise(df, LATEST_INDEED, ALL_TIME_INDEED, "Indeed", is_linkedin=False)


def run_scrape_ba():
    from src.config import get_max_days, get_window_tag
    max_days = get_max_days()
    window_tag = get_window_tag()
    logger.info("\n" + "=" * 46)
    logger.info("  Bundesagentur Scraper")
    logger.info(f"  Window : last {max_days} day(s)  ({window_tag})")
    logger.info(f"  Queries: {len(BA_BROAD_QUERIES)} search terms")
    logger.info(f"  Output : {LATEST_BA}  |  {ALL_TIME_BA}")
    logger.info("=" * 46 + "\n")

    purge_empty_desc_from_all_time(ALL_TIME_BA)

    from src.scrapers.ba import scrape_arbeitsagentur

    ba_frames = []
    for query in BA_BROAD_QUERIES:
        try:
            jobs = scrape_arbeitsagentur(query, max_results=BA_MAX_RESULTS)
            count = len(jobs)
            if count:
                df = pd.DataFrame(jobs)
                ba_frames.append(df)
            logger.info(f"  '{query[:40]}...': {count} rows")
        except Exception as exc:
            logger.info(f"  Warning: '{query[:40]}...' failed: {exc}")
        time.sleep(1)

    ba_df = pd.concat(ba_frames, ignore_index=True) if ba_frames else pd.DataFrame()
    if not ba_df.empty:
        logger.info(f"\n  Raw Bundesagentur jobs: {len(ba_df)}")
        ba_df = apply_filters(ba_df, is_linkedin=False)

    finalise(ba_df, LATEST_BA, ALL_TIME_BA, "Bundesagentur", is_linkedin=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Karriere Pipeline Scraper Orchestrator")
    parser.add_argument("--linkedin", action="store_true", help="Run LinkedIn scraper")
    parser.add_argument("--indeed", action="store_true", help="Run Indeed scraper")
    parser.add_argument("--ba", action="store_true", help="Run Bundesagentur scraper")
    args = parser.parse_args()

    if args.linkedin:
        run_scrape_linkedin()
    elif args.indeed:
        run_scrape_indeed()
    elif args.ba:
        run_scrape_ba()
    else:
        logger.info("  Running full scraper pipeline...")
        run_scrape_linkedin()
        run_scrape_indeed()
        run_scrape_ba()


from src.scrapers.bund import run_scrape_bund
from src.scrapers.xing import run_scrape_xing
