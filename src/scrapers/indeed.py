"""
scrapers/indeed.py  —  Indeed Germany scraper wrapper 

Public API:
    scrape_indeed(title, results_wanted, hours_old) -> pd.DataFrame | None

Uses jobspy under the hood. Returns a raw DataFrame (no filtering applied).
"""

import pandas as pd
# pyrefly: ignore [missing-import]
from jobspy import scrape_jobs

from src.config import INDEED_RESULTS_WANTED, get_indeed_hours_old


def scrape_indeed(
    title: str,
    results_wanted: int = INDEED_RESULTS_WANTED,
    hours_old: int | None = None,
    offset: int = 0,
    location: str | None = None,
    country_indeed: str | None = None,
) -> pd.DataFrame | None:
    """
    Scrape Indeed for a single job title with configurable regional geo targeting.
    Supports offset parameter for pagination.

    Returns a raw DataFrame from jobspy, or empty DataFrame on failure.
    Caller is responsible for concatenating results and running filters.
    """
    if hours_old is None:
        hours_old = get_indeed_hours_old()
    target_loc = location or "Germany"
    target_country = (country_indeed or "germany").lower()
    try:
        return scrape_jobs(
            site_name=["indeed"],
            search_term=title,
            location=target_loc,
            results_wanted=results_wanted,
            hours_old=hours_old,
            offset=offset,
            job_type="fulltime",
            country_indeed=target_country,
            indeed_fetch_description=True,
        )
    except Exception as exc:
        print(f"[WARNING] Indeed scrape for '{title}' (offset={offset}, loc={target_loc}) failed: {exc}")
        return pd.DataFrame()
