"""
file_io.py  —  File system operations, CSV saving, and cross-portal deduplication log tracking.
"""

import os
import csv
from datetime import datetime, timezone
import pandas as pd

from src.core.dedup import (
    canonical_job_url,
    dedup_job_dataframe,
    extract_location_key,
    extract_req_id,
    extract_title_tokens,
    normalize_company_entity,
    normalize_title_entity,
    plain_url,
)
from src.core.utils import _norm
from src.core.logger import get_logger
logger = get_logger(__name__)


def _save_csv(df: pd.DataFrame, path: str) -> None:
    """Save DataFrame to CSV, ensuring directory exists and formatting URLs."""
    df = df.copy()
    if "job_url" in df.columns:
        df["job_url"] = df["job_url"].apply(plain_url)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    df.to_csv(tmp_path, index=False, quoting=csv.QUOTE_ALL)
    os.replace(tmp_path, path)


def dedup(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate jobs by URL, requisition code, composite key, and semantic title+location."""
    return dedup_job_dataframe(df)


def rebuild_all_time_combined() -> None:
    """
    Read all portal job records and produce data/all_combined.csv
    with cross-portal deduplication.

    Dedup strategy:
      Delegates to src.core.dedup.dedup_job_dataframe for 5-tier deduplication
      (canonical URL, ATS requisition code, exact company+title, tokenized title+location,
      and fuzzy title similarity).
    """
    from src.config import ALL_TIME_LINKEDIN, ALL_TIME_INDEED, ALL_TIME_BA, ALL_TIME_BUND, ALL_TIME_XING, ALL_TIME_COMBINED

    portal_files = [ALL_TIME_LINKEDIN, ALL_TIME_INDEED, ALL_TIME_BA, ALL_TIME_BUND, ALL_TIME_XING]
    frames = []
    for f in portal_files:
        try:
            df = pd.read_csv(f) if os.path.exists(f) else pd.DataFrame()
            if not df.empty:
                frames.append(df)
        except Exception as exc:
            logger.warning(f"  [combined] Could not read {f}: {exc}")

    if not frames:
        logger.info("  [combined] No all-time files found — skipping rebuild.")
        return

    combined = pd.concat(frames, ignore_index=True)

    # Unified 5-tier deduplication keeping richest description
    before = len(combined)
    combined = dedup_job_dataframe(combined, keep_longest_desc=True)

    # 3. Apply active pipeline filters, date cutoff (30d max), and candidate match scoring to ensure all_combined.csv is clean
    from src.filters import apply_filters
    combined = apply_filters(combined, max_days=30)
    combined = combined.reset_index(drop=True)

    _save_csv(combined, ALL_TIME_COMBINED)
    logger.info(
        f"  [combined] Rebuilt {ALL_TIME_COMBINED}: "
        f"{before} raw rows -> {len(combined)} after cross-portal dedup & filtering"
    )
    
    try:
        from src.config import BEST_JOBS_FILE
        top_matches = combined[combined.get("score", 0) >= 40].copy() if "score" in combined.columns else combined
        if not top_matches.empty:
            _save_csv(top_matches, BEST_JOBS_FILE)
    except Exception as best_err:
        logger.warning(f"  [combined] Failed to save best jobs CSV: {best_err}")

def update_all_time(new_df: pd.DataFrame, all_time_file: str) -> None:
    """Append new jobs to the all-time tracker log, keeping only unique jobs.
    After updating the portal-specific file, rebuilds the combined CSV.
    """
    if new_df.empty:
        return
    from src.core.utils import get_german_now
    now_dt = get_german_now()
    today = now_dt.strftime("%Y-%m-%d")
    now_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    new_df = new_df.copy()
    new_df["first_seen"] = today
    if "scraped_at" not in new_df.columns or new_df["scraped_at"].isna().all():
        new_df["scraped_at"] = now_ts
    existing = pd.read_csv(all_time_file) if os.path.exists(all_time_file) else pd.DataFrame()

    combined = pd.concat([new_df, existing], ignore_index=True)
    if "job_url" in combined.columns:
        combined = combined.drop_duplicates(subset=["job_url"], keep="first")
    combined = combined.copy()
    combined["_key"] = (
        combined.get("title",   pd.Series("", index=combined.index)).fillna("").apply(_norm)
        + "|||"
        + combined.get("company", pd.Series("", index=combined.index)).fillna("").apply(_norm)
    )
    combined = combined.drop_duplicates(subset=["_key"], keep="first").drop(columns=["_key"])
    _save_csv(combined, all_time_file)
    logger.info(f"  All-time log:      {len(combined)} total rows -> {all_time_file}")

    # Rebuild the cross-portal combined file after every portal update
    rebuild_all_time_combined()


def purge_empty_desc_from_all_time(all_time_file: str) -> None:
    """
    Remove rows with empty description that were added today (from a broken run).
    Keeps the CSV clean and prevents them blocking URL dedup on the next run.
    """
    try:
        if not os.path.exists(all_time_file):
            return
        else:
            df = pd.read_csv(all_time_file)
    except Exception:
        return
    if df.empty:
        return
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    before = len(df)
    empty_desc = df.get("description", pd.Series("", index=df.index)).fillna("").str.strip() == ""
    seen_today = df.get("first_seen",  pd.Series("", index=df.index)).fillna("").str.strip() == today
    mask_remove = empty_desc & seen_today
    removed = int(mask_remove.sum())
    if removed:
        df = df[~mask_remove].reset_index(drop=True)
        _save_csv(df, all_time_file)
        logger.info(f"  [startup] Purged {removed} empty-desc row(s) added today from {all_time_file} ({before} → {len(df)} rows)")
    else:
        logger.info(f"  [startup] No empty-desc rows to purge from {all_time_file} ({before} rows intact)")
