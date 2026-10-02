"""
scrapers/ba.py  —  Bundesagentur für Arbeit scraper 

Public API:
    scrape_arbeitsagentur(query, max_results) -> list[dict]
"""

import base64
import time
from datetime import datetime, timedelta, timezone

import requests

from src.config import MAX_DAYS
from src.core.logger import get_logger
logger = get_logger(__name__)

# v6 was tested but returns empty stellenangebote — reverted to v4/jobs which is
# confirmed working. v4/app/jobs is the alternative mobile endpoint but also untested.
# Revisit v6 if BA deprecates v4.
_SEARCH_URL    = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
_SEARCH_V4_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
_DETAIL_V4     = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails"
_DETAIL_V2     = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v2/jobdetails"
_HEADERS = {
    "X-API-Key":  "jobboerse-jobsuche",
    "User-Agent": "Mozilla/5.0 (compatible; JobScraper/1.0)",
}


def _fetch_external_job_description(url: str) -> str:
    """Fetch the HTML of the external URL, convert it to clean markdown/text."""
    try:
        from bs4 import BeautifulSoup
        import markdownify
        import re

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10, verify=True)
        if not resp.ok:
            return ""

        soup = BeautifulSoup(resp.content, "html.parser")
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        text = markdownify.markdownify(str(soup), heading_style="ATX").strip()
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
    except Exception as e:
        logger.warning(f"Failed to fetch external description from {url}: {e}")
        return ""


def _extract_ba_description(d_data: dict) -> str:
    """
    Extract the job description from a BA detail API response.
    Tries stellenangebotsBeschreibung first, then legacy field names.
    """
    val = d_data.get("stellenangebotsBeschreibung")
    if val:
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for sub in ("inhalt", "text", "beschreibung", "freitext", "content"):
                sv = val.get(sub)
                if sv and isinstance(sv, str) and sv.strip():
                    return sv.strip()
            parts = [str(v) for v in val.values() if isinstance(v, str) and str(v).strip()]
            if parts:
                return " ".join(parts).strip()

    for key in ("stellenbeschreibung", "beschreibung", "freitext", "jobDescription",
                "description", "aufgaben", "qualifikationen", "taetigkeit"):
        v = d_data.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip()

    for nested_key, sub_keys in [
        ("stelle",         ("stellenbeschreibung", "beschreibung", "freitext", "jobDescription", "aufgaben", "qualifikationen")),
        ("stellenangebot", ("stellenbeschreibung", "beschreibung", "freitext", "aufgaben", "qualifikationen")),
    ]:
        nested = d_data.get(nested_key) or {}
        if isinstance(nested, dict):
            for key in sub_keys:
                v = nested.get(key)
                if v and isinstance(v, str) and v.strip():
                    return v.strip()

    logger.info(f"    [BA detail] description not found. Top-level keys: {list(d_data.keys())[:20]}")
    return ""


def _ba_search_fallback(job: dict) -> str:
    for key in ("kurzBeschreibung", "kurzbeschreibung", "stellenbeschreibung",
                "beschreibung", "freitext", "aufgaben", "qualifikationen", "taetigkeit"):
        val = job.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def scrape_arbeitsagentur(query: str, max_results: int = 25) -> list[dict]:
    """
    Fetch jobs from the Bundesagentur fur Arbeit public REST API.

    Description resolution order:
      1. v4 detail endpoint  (newer, more reliable)
      2. v2 detail endpoint  (legacy fallback)
      3. Search-result text fields via _ba_search_fallback()

    NOTE on intentionally omitted params:
      - `ct` (Vertragsart): omitted — ct=zeitarbeit restricts to temp-agency
        contracts only, filtering out Festanstellung / direct-hire positions.
      - `umkreis`: omitted — meaningless for a country-wide wo=Deutschland search.
      - `arbeitszeit`: omitted — vz (Vollzeit only) was silently dropping jobs posted
        as flexible (vz,tz) or with no arbeitszeit set, common at startups and
        research institutions. Post-filter in filters.py handles part-time if needed.
    """
    from src.config import get_max_days
    max_days  = get_max_days()
    cutoff    = datetime.now(tz=timezone.utc) - timedelta(days=max_days)
    results: list[dict] = []
    page      = 1
    page_size = min(max_results, 100)
    fetched   = 0

    while fetched < max_results:
        params = {
            "was":                 query,
            "wo":                  "Deutschland",
            "angebotsart":         "1",      # Arbeit only (no apprenticeships/internships)
            "pav":                 "false",  # exclude private Personalvermittlung agencies
            "page":                page,
            "size":                page_size,
            "veroeffentlichtseit": max_days, # Server-side date pre-filter (last N days)
        }
        data = {}
        for search_url in [_SEARCH_URL, _SEARCH_V4_URL]:
            try:
                resp = requests.get(search_url, params=params, headers=_HEADERS, timeout=15, verify=True)
                if resp.ok:
                    data = resp.json()
                    if data.get("ergebnisliste") or data.get("stellenangebote"):
                        break
            except Exception as e:
                logger.info(f"    BA search error ({search_url} page {page}): {e}")

        jobs = data.get("ergebnisliste") or data.get("stellenangebote") or []
        if not jobs:
            break

        for job in jobs:
            if fetched >= max_results:
                break

            modified = (
                job.get("datumErsteVeroeffentlichung") or
                job.get("aktuelleVeroeffentlichungsdatum") or
                (job.get("veroeffentlichungszeitraum", {}).get("von") if isinstance(job.get("veroeffentlichungszeitraum"), dict) else "") or
                job.get("eintrittsdatum", "")
            )
            job_dt = None
            if modified:
                try:
                    job_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                    if job_dt.tzinfo is None:
                        job_dt = job_dt.replace(tzinfo=timezone.utc)
                    if job_dt < cutoff:
                        continue
                except Exception:
                    pass

            ref_nr  = job.get("referenznummer") or job.get("refnr", "")
            job_url = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref_nr}" if ref_nr else ""
            fallback_desc = _ba_search_fallback(job)
            description   = ""

            if ref_nr:
                encoded = base64.b64encode(ref_nr.encode()).decode()
                for endpoint, label in [(_DETAIL_V4, "v4"), (_DETAIL_V2, "v2")]:
                    try:
                        d_resp = requests.get(f"{endpoint}/{encoded}", headers=_HEADERS, timeout=10, verify=True)
                        if d_resp.ok:
                            d_json = d_resp.json()
                            description = _extract_ba_description(d_json)

                            ext_url = d_json.get("externeURL")
                            if ext_url and (not description or len(description) < 200):
                                logger.info(f"    [BA detail] Description short — fetching externeURL: {ext_url}")
                                ext_desc = _fetch_external_job_description(ext_url)
                                if ext_desc:
                                    description = ext_desc

                            if description:
                                break
                    except Exception as ex:
                        logger.info(f"    [BA {label} detail] exception for refnr={ref_nr}: {ex}")
                time.sleep(0.3)

            if not description:
                description = fallback_desc

            title = job.get("stellenangebotsTitel") or job.get("titel") or ""
            firma = job.get("firma") or job.get("arbeitgeber", {})
            company = firma.get("name", "") if isinstance(firma, dict) else str(firma)

            if "stellenlokationen" in job and job["stellenlokationen"]:
                adresse = job["stellenlokationen"][0].get("adresse", {})
                ort = adresse.get("ort", "")
                plz = adresse.get("plz", "")
                location = f"{ort} {plz}".strip() if ort else "Deutschland"
            else:
                arbeitsort = job.get("arbeitsort", {}) or {}
                if isinstance(arbeitsort, dict):
                    ort      = arbeitsort.get("ort", "")
                    plz      = arbeitsort.get("plz", "")
                    location = f"{ort} {plz}".strip() if ort else "Deutschland"
                else:
                    location = str(arbeitsort)

            results.append({
                "title":       title,
                "company":     company,
                "location":    location,
                "date_posted": job_dt.strftime("%Y-%m-%d") if job_dt else "",
                "job_url":     job_url,
                "description": description,
            })
            fetched += 1

        page += 1
        time.sleep(0.5)

    return results
