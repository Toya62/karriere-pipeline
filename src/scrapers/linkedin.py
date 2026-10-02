# scrapers/linkedin.py  —  High-speed Two-Phase LinkedIn Scraper with Exact Timestamps 

import os
import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
# pyrefly: ignore [missing-import]
from jobspy import scrape_jobs

from src.config import LINKEDIN_RESULTS_WANTED, MAX_APPLICANTS, get_linkedin_hours_old
from src.core.logger import get_logger

logger = get_logger(__name__)

_COOKIE_EXPIRED_WARNED = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

def _get_auth_session() -> tuple[requests.Session | None, str | None]:
    li_at = os.environ.get("LINKEDIN_LI_AT", "").strip()
    if not li_at:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env_path = os.path.join(root_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("LINKEDIN_LI_AT="):
                            li_at = line.split("=", 1)[1].strip().strip('"\'')
                            break
            except Exception:
                pass
    if not li_at:
        return None, None

    s = requests.Session()
    s.cookies.set("li_at", li_at, domain=".linkedin.com")
    s.cookies.set("JSESSIONID", "\"ajax:1234567890\"", domain=".linkedin.com")
    return s, li_at

def extract_job_id(url_or_id: str) -> str | None:
    if not url_or_id:
        return None
    s = str(url_or_id).strip()
    if s.isdigit():
        return s
    m = re.search(r"view/([0-9]+)", s)
    if m:
        return m.group(1)
    m2 = re.search(r"currentJobId=([0-9]+)", s)
    if m2:
        return m2.group(1)
    return None

def fetch_single_job_details(job_url: str, session: requests.Session | None = None) -> dict:
    jid = extract_job_id(job_url)
    if not jid:
        return {}

    # 1. Try Voyager API (Exact millisecond timestamp & applicant count)
    auth_sess = session
    if auth_sess is None:
        auth_sess, _ = _get_auth_session()

    if auth_sess:
        v_headers = {
            "User-Agent": HEADERS["User-Agent"],
            "csrf-token": "ajax:1234567890",
            "x-restli-protocol-version": "2.0.0",
            "Accept": "application/vnd.linkedin.normalized+json+2.1"
        }
        v_url = f"https://www.linkedin.com/voyager/api/jobs/jobPostings/{jid}?decorationId=com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-65"
        try:
            v_resp = auth_sess.get(v_url, headers=v_headers, timeout=8)
            # 302 redirect = expired cookie (LinkedIn redirects stale sessions instead of returning 401/403)
            if v_resp.status_code in (401, 403, 302):
                global _COOKIE_EXPIRED_WARNED
                if not _COOKIE_EXPIRED_WARNED:
                    reason = "302 redirect (session expired/invalid)" if v_resp.status_code == 302 else f"HTTP {v_resp.status_code} Unauthorized"
                    logger.warning(f"⚠️ [LinkedIn] Voyager API returned {reason}. LINKEDIN_LI_AT session cookie may be expired or invalid.")
                    _COOKIE_EXPIRED_WARNED = True
                    try:
                        from src.core.notifier import send_whatsapp_alert
                        send_whatsapp_alert(f"🔑 *LinkedIn Cookie Alert*\n\nVoyager API returned {reason}. Please refresh LINKEDIN_LI_AT in GitHub Secrets.")
                    except Exception:
                        pass
            elif v_resp.status_code == 200:
                data = v_resp.json().get("data", {})
                listed_at = data.get("listedAt")
                app_count = data.get("applies")
                desc_text = data.get("description", {}).get("text", "")
                
                date_str = ""
                age_hours = None
                if listed_at:
                    dt = datetime.fromtimestamp(listed_at / 1000.0, tz=timezone.utc)
                    date_str = dt.strftime("%Y-%m-%d")
                    age_hours = (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600.0

                if desc_text:
                    return {
                        "applicant_count": app_count,
                        "description": desc_text,
                        "date_posted": date_str,
                        "age_hours": age_hours
                    }
        except Exception:
            pass

    # 2. Fallback to public guest endpoint
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return {}
        
        text = resp.text
        # Applicant count
        app_num = None
        m_app = re.search(r"class=\"num-applicants__caption\"[^>]*>([^<]+)<", text)
        if not m_app:
            m_app = re.search(r"([0-9]+\+?\s*(?:applicants?|Bewerber|applicant|people\s+clicked\s+apply)|over\s+[0-9]+\s+(?:applicants?|people\s+clicked\s+apply|Bewerber)|first\s+[0-9]+\s+applicants?)", text, re.IGNORECASE)
        
        if m_app:
            app_text = m_app.group(1).strip()
            num_m = re.search(r"([0-9]+)", app_text)
            if num_m:
                app_num = int(num_m.group(1))
                if "over" in app_text.lower():
                    app_num = app_num + 1

        # Description Markdown
        soup = BeautifulSoup(text, "html.parser")
        desc_el = soup.find("div", class_="show-more-less-html__markup")
        desc_md = md(str(desc_el)).strip() if desc_el else ""

        return {
            "applicant_count": app_num,
            "description": desc_md,
            "date_posted": "",
            "age_hours": None
        }
    except Exception as e:
        logger.debug(f"Error fetching details for {job_url}: {e}")
        return {}

def scrape_linkedin(
    title: str,
    results_wanted: int = LINKEDIN_RESULTS_WANTED,
    hours_old: int | None = None,
) -> pd.DataFrame | None:
    """
    Phase 1: Ultra-fast metadata scrape (no descriptions) in ~2-5s per query.
    """
    if hours_old is None:
        hours_old = get_linkedin_hours_old()
    try:
        return scrape_jobs(
            site_name=["linkedin"],
            search_term=title,
            location="Germany",
            results_wanted=results_wanted,
            hours_old=hours_old,
            job_type="fulltime",
            linkedin_fetch_description=True,
        )
    except Exception as exc:
        logger.warning(f"LinkedIn scrape for '{title}' failed: {exc}")
        return pd.DataFrame()

def hydrate_linkedin_jobs(df: pd.DataFrame, max_workers: int = 8, max_hours_old: int | None = None) -> pd.DataFrame:
    """
    Phase 2: Parallel hydration of exact timestamp, full description + live applicant count.
    """
    if df.empty or "job_url" not in df.columns:
        return df

    df = df.copy()
    if "applicant_count" not in df.columns:
        df["applicant_count"] = None

    urls_to_fetch = []
    for idx, row in df.iterrows():
        url = str(row.get("job_url", ""))
        desc = str(row.get("description", "") or "").strip()
        if url and ("linkedin.com" in url.lower()) and (not desc or pd.isna(row.get("applicant_count")) or pd.isna(row.get("date_posted")) or not str(row.get("date_posted", "")).strip()):
            urls_to_fetch.append((idx, url))

    if not urls_to_fetch:
        return df

    logger.info(f"⚡ Concurrently hydrating {len(urls_to_fetch)} LinkedIn jobs with exact timestamps & applicant counts...")

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(fetch_single_job_details, url): (idx, url)
            for idx, url in urls_to_fetch
        }
        for future in as_completed(future_to_idx):
            idx, url = future_to_idx[future]
            try:
                data = future.result()
                if data:
                    results[idx] = data
            except Exception:
                pass

    drop_indices = []
    cutoff_hours = max_hours_old if max_hours_old is not None else get_linkedin_hours_old()

    for idx, data in results.items():
        if data.get("description"):
            df.at[idx, "description"] = data["description"]
        if data.get("applicant_count") is not None:
            df.at[idx, "applicant_count"] = data["applicant_count"]
        if data.get("date_posted"):
            df.at[idx, "date_posted"] = data["date_posted"]
            
        # Strict 24h filter check based on exact millisecond timestamp
        age_h = data.get("age_hours")
        if age_h is not None and age_h > (cutoff_hours + 4.0):  # 4h buffer for timezone variances
            drop_indices.append(idx)

    # RETRY PASS: Any jobs that still have empty descriptions after first hydration
    # LinkedIn guest endpoint sometimes returns empty on first request (new/recently updated jobs).
    # We wait 2s and retry once.
    still_empty = []
    for idx, row in df.iterrows():
        url = str(row.get("job_url", ""))
        desc = str(row.get("description", "") or "").strip()
        if url and "linkedin.com" in url.lower() and not desc:
            still_empty.append((idx, url))
    if still_empty:
        import time as _time
        logger.info(f"🔄 Retrying description fetch for {len(still_empty)} still-empty jobs (2s delay)...")
        _time.sleep(2)
        for idx, url in still_empty:
            retry_data = fetch_single_job_details(url)
            if retry_data and retry_data.get("description"):
                df.at[idx, "description"] = retry_data["description"]
                logger.info(f"  ✅ Retry succeeded: {url}")
            else:
                logger.warning(f"  ❌ Retry failed (desc still empty): {url}")

    if drop_indices:
        logger.info(f"⏳ Dropped {len(drop_indices)} reposted/older jobs exceeding {cutoff_hours}h window.")
        df = df.drop(index=drop_indices).reset_index(drop=True)

    logger.info(f"✅ Successfully hydrated and validated {len(results)} jobs.")
    return df
