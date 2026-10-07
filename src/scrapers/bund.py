"""
scrapers/bund.py — Service.bund.de & Interamt Job Scraper 
Fetches official German public sector, research institutes (DLR, Fraunhofer, Max-Planck, FZ Jülich),
and state IT providers (TV-L / TVöD / TV-H).
"""

import os
import re
import time
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import ALL_TIME_BUND, WINDOW_TAG
from src.core.logger import get_logger

logger = get_logger(__name__)

GERMAN_TZ = ZoneInfo("Europe/Berlin")

BUND_QUERIES = [
    "Data Engineer",
    "Python",
    "Wissenschaftlicher Mitarbeiter Informatik",
    "Research Software Engineer",
    "Cloud Engineer",
    "DevOps",
    "Softwareentwickler",
    "Datenanalyse",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def _clean_text(html_text: str) -> str:
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    for s in soup(["script", "style", "nav", "footer", "header"]):
        s.extract()
    text = soup.get_text(separator="\n")
    # Soft hyphens (\xad / &shy;) are presentational — service.bund.de
    # breaks compound words with them (e.g. "Soft\xadwa\xadre\xadent").
    # Downstream regex in filters.py does not account for \xad, so every
    # keyword match silently fails. Strip them before normalising whitespace.
    text = text.replace("\u00ad", "").replace("&shy;", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fetch_bund_job_detail(url: str) -> dict:
    """Fetches full job description and metadata from the service.bund.de posting page."""
    clean_url = url.split("#")[0]
    try:
        resp = requests.get(clean_url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return {"job_url": clean_url, "description": ""}
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find main content container
        content_el = soup.find("div", class_="content") or soup.find("main") or soup.find("div", id="content") or soup.body
        desc_text = _clean_text(str(content_el)) if content_el else ""

        # Extract employer and location if present in header table or <p> labels.
        # The site has moved some postings away from <tr><th>/<td> tables
        # to plain <p>Arbeitgeber: …</p> paragraphs — checking only the
        # table form silently left company and location empty for those.
        company = ""
        location = ""
        for row in soup.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if th and td:
                th_t = th.get_text(strip=True).lower()
                td_t = td.get_text(strip=True)
                if "arbeitgeber" in th_t or "organisation" in th_t:
                    company = td_t
                elif "dienstort" in th_t or "arbeitsort" in th_t or "ort" in th_t:
                    location = td_t

        if not company or not location:
            for p in soup.find_all("p"):
                pt = p.get_text(" ", strip=True)
                low = pt.lower()
                if not company and ("arbeitgeber" in low or "organisation" in low or "arbeitgeber:" in low):
                    company = re.sub(r"^(arbeitgeber|organisation)\s*:\s*", "", pt, flags=re.I).strip()
                elif not location and ("dienstort" in low or "arbeitsort" in low or "ort:" in low):
                    location = re.sub(r"^((dienstort|arbeitsort|ort))\s*:\s*", "", pt, flags=re.I).strip()

        return {
            "job_url": clean_url,
            "description": desc_text,
            "company": company,
            "location": location,
        }
    except Exception as e:
        logger.debug(f"[Bund.de] Failed fetching {clean_url}: {e}")
        return {"job_url": clean_url, "description": ""}


def scrape_bund(queries: list[str] = None, max_results_per_query: int = 40) -> pd.DataFrame:
    """
    Scrapes service.bund.de RSS feeds across queries, concurrent hydration of full descriptions.
    """
    search_queries = queries or BUND_QUERIES
    logger.info(f"🏛️ Starting Bund.de / Public Sector scrape across {len(search_queries)} queries...")

    seen_urls = set()
    raw_items = []

    for q in search_queries:
        encoded_q = requests.utils.quote(q)
        rss_url = f"https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html?resultsPerPage={max_results_per_query}&templateQueryString={encoded_q}&sortOrder=dateOfIssue_dt+desc&jobsrss=true"
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else []
            for item in items:
                link = (item.findtext("link", "") or "").strip().split("#")[0]
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)
                title = (item.findtext("title", "") or "").strip()
                pub_date = (item.findtext("pubDate", "") or "").strip()
                desc_snippet = item.findtext("description", "") or ""

                # Parse date to YYYY-MM-DD
                date_str = ""
                if pub_date:
                    try:
                        # e.g., 'Fri, 18 Sep 2026 00:01:20 +0200'
                        parsed_dt = datetime.strptime(pub_date[:16], "%a, %d %b %Y")
                        date_str = parsed_dt.strftime("%Y-%m-%d")
                    except Exception:
                        date_str = datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")
                else:
                    date_str = datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

                # Extract employer from RSS description snippet
                company = ""
                m_comp = re.search(r"Arbeitgeber:\s*<strong>(.*?)</strong>", desc_snippet, re.IGNORECASE)
                if m_comp:
                    company = BeautifulSoup(m_comp.group(1), "html.parser").get_text(strip=True)

                location = ""
                m_loc = re.search(r"Ort:\s*<strong>(.*?)</strong>", desc_snippet, re.IGNORECASE)
                if m_loc:
                    location = BeautifulSoup(m_loc.group(1), "html.parser").get_text(strip=True)

                raw_items.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "date_posted": date_str,
                    "job_url": link,
                    "description": "",
                    "missing_keywords": "",
                    "applicant_count": None,
                    "scraped_at": datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                })
        except Exception as e:
            logger.warning(f"[Bund.de] Failed search for '{q}': {e}")

    logger.info(f"🏛️ Bund.de RSS returned {len(raw_items)} candidate postings. Hydrating full descriptions...")
    if not raw_items:
        return pd.DataFrame(columns=[
            "title", "company", "location", "date_posted", "job_url",
            "description", "missing_keywords", "applicant_count", "scraped_at"
        ])

    # Concurrent full description fetch
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(fetch_bund_job_detail, it["job_url"]): idx
            for idx, it in enumerate(raw_items)
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                detail = future.result()
                if detail.get("description"):
                    raw_items[idx]["description"] = detail["description"]
                if detail.get("company") and not raw_items[idx]["company"]:
                    raw_items[idx]["company"] = detail["company"]
                if detail.get("location") and not raw_items[idx]["location"]:
                    raw_items[idx]["location"] = detail["location"]
            except Exception:
                pass

    df = pd.DataFrame(raw_items)
    # Filter out empty descriptions
    df = df[df["description"].str.len() > 50].reset_index(drop=True)
    logger.info(f"✅ Bund.de scraping completed: {len(df)} validated postings.")
    return df


def run_scrape_bund(window: str = None) -> pd.DataFrame:
    """Standard orchestrator runner for Bund.de."""
    from src.filters import (
        filter_date, filter_seniority, filter_experience, filter_noise,
        filter_cs_relevance, filter_research_cs, filter_forbidden_tech,
        filter_language, filter_job_type, filter_seen_reposts, filter_seen_reposts_by_url
    )
    from src.db.database import save_jobs_to_db

    df = scrape_bund()
    if df.empty:
        logger.info("[Bund.de] No jobs found.")
        return df

    before = len(df)
    df = filter_date(df)
    df = filter_noise(df)
    df = filter_seniority(df)
    df = filter_cs_relevance(df)
    df = filter_forbidden_tech(df)
    df = filter_language(df)
    df = filter_job_type(df)
    df = filter_seen_reposts(df)
    df = filter_seen_reposts_by_url(df)

    logger.info(f"🏛️ Bund.de Filter Pipeline: {len(df)} / {before} kept after dedup & filters.")
    if not df.empty:
        saved_cnt = save_jobs_to_db(df)
        logger.info(f"🏛️ Bund.de: Persisted {saved_cnt} fresh unique jobs to SQLite data/karriere.db")
    return df
