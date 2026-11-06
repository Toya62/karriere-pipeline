"""
utils.py  —  Low-level text utilities 

Import from here for any text cleaning or URL normalisation.
"""

import html
import re
import pandas as pd

# ── HTML → plain text ─────────────────────────────────────────────────────────
_TAG_RE       = re.compile(r"<[^>]+>")
_MULTI_NL_RE  = re.compile(r"\n{3,}")
_MULTI_SPC_RE = re.compile(r"[^\S\n]{2,}")
_BLOCK_TAG_RE = re.compile(
    r"</?\s*(p|br|li|ul|ol|h[1-6]|div|section|article|header|footer|tr|td|th)"
    r"(?:\s[^>]*)?>\s*", re.IGNORECASE,
)


def _clean_desc(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    text = html.unescape(raw)
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = _MULTI_SPC_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


_MD_LINK_RE = re.compile(r"^\[([^\]]*)\]\(([^)]+)\)$")


def _plain_url(value: str) -> str:
    if not isinstance(value, str):
        return value
    value = value.strip()
    m = _MD_LINK_RE.match(value)
    return m.group(2).strip() if m else value


_DIGITS_RE = re.compile(r"(\d+)")


def _parse_applicant_count(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, float):
        return None if pd.isna(val) else int(val)
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "nat", "", "unknown"):
        return None
    m = _DIGITS_RE.search(s)
    return int(m.group(1)) if m else None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).lower().strip())


def normalize_company_entity(s: str) -> str:
    """Canonical company normalization for cross-portal and historical deduplication.

    Strips legal suffixes, branch designations (e.g. 'Hauptsitz Berlin', 'Destatis'),
    subsidiary/agency tags, and punctuation so that:
      'aconium GmbH' == 'aconium GmbH (Hauptsitz Berlin)'
      'Statistisches Bundesamt (Destatis)' == 'Statistisches Bundesamt'
      'Advantest Europe GmbH' == 'Advantest'
    """
    if not s or not isinstance(s, str):
        return ""
    text = s.lower().strip()
    # Strip parenthetical annotations: (Destatis), (Hauptsitz ...), (Europe), etc.
    text = re.sub(r"\(.*?\)", "", text)
    # Strip common legal, corporate, and branch designations
    clean = re.sub(
        r"\b(gmbh|ag|co|kg|kgaa|se|inc|corp|ltd|s\.a\.|ug|haftungsbeschr\u00e4nkt|holding|group|gruppe|"
        r"solutions|services|technologies|systems|international|dach|"
        r"europe|deutschland|germany|hauptsitz|niederlassung|city|land\s+bw|land\s+bayern)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Replace non-alphanumeric with spaces and clean up
    clean = re.sub(r"[^a-z0-9]+", " ", clean)
    stripped = " ".join(clean.split()).strip()
    if stripped:
        return stripped
    # Fallback if entire company name consisted of matched tokens
    fallback = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(fallback.split()).strip()


def normalize_title_entity(s: str) -> str:
    """Canonical title normalization for deduplication across portals.

    Strips gender markers (m/w/d, all genders, etc.), trailing punctuation,
    and brackets.
    """
    if not s or not isinstance(s, str):
        return ""
    text = s.lower().strip()
    # Strip gender annotations: (m/w/d), (f/m/d), (all genders), (gn), [m/w/d], etc.
    text = re.sub(
        r"[\(\[\/]\s*(?:all\s+genders?|gn|[mwdfx][\/\-\|\s]*[mwdfx]?[\/\-\|\s]*[mwdfx]?)\s*[\)\]\/]?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(all\s+genders?|gn|m\/w\/d|f\/m\/d|m\/f\/d|w\/m\/d|d\/w\/m|m\/w\/x)\b", "", text, flags=re.IGNORECASE)
    # Strip trailing dashes or slashes
    text = re.sub(r"[-–—\/]+$", "", text).strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split()).strip()


def _normalize_company(s: str) -> str:
    s = str(s).lower().strip()
    s = re.sub(r"\b(gmbh|ag|co|kg|se|inc|corp|ltd|s\.a\.|university|universität|uni|hochschule)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "-")


def _has_desc(d: str) -> bool:
    return bool(str(d).strip())


_REQ_ID_RE = re.compile(
    r"(?:referenzcode|kennziffer|referenznummer|stellennummer|referenz-nr\.?)[^0-9\n]{0,50}?([0-9]{4,}[-_][0-9]{2,})",
    re.I
)

def _extract_req_id(desc: str) -> str | None:
    """Extracts base requisition/reference code from job description text (e.g. 20261895 from 20261895_0002)."""
    if not desc or not isinstance(desc, str):
        return None
    clean = desc.replace("\\", "")
    m = _REQ_ID_RE.search(clean)
    if m:
        full_code = m.group(1)
        base = full_code.split("_")[0].split("-")[0]
        return base if len(base) >= 4 else None
    return None


_GENDER_NOISE_RE = re.compile(
    r"\(?\b(?:m/w/d|w/m/d|d/m/w|m/f/d|w/m/i|gn|all genders)\)?|[/:\*](?:in|r)\b",
    re.I
)
_TITLE_STOPWORDS = {
    "im", "bereich", "für", "fuer", "und", "von", "in", "m", "w", "d",
    "mitarbeiterin", "mitarbeiter", "wissenschaftliche", "wissenschaftlicher"
}

def _extract_title_tokens(title: str) -> set[str]:
    """Extracts clean semantic keyword tokens from a job title, removing gender tags and boilerplate."""
    if not title:
        return set()
    s = _GENDER_NOISE_RE.sub(" ", str(title).lower())
    s = re.sub(r"[^a-z0-9äöüß]+", " ", s)
    return {w for w in s.split() if len(w) > 2 and w not in _TITLE_STOPWORDS}


def _extract_location_key(location: str) -> str:
    """Extracts 5-digit postal code or normalized primary city name for location matching."""
    if not location:
        return ""
    s = str(location).lower().strip()
    m = re.search(r"\b(\d{5})\b", s)
    if m:
        return m.group(1)
    parts = [p.strip() for p in re.split(r"[,/]", s) if p.strip()]
    return parts[0] if parts else ""


from zoneinfo import ZoneInfo
from datetime import datetime, timezone

GERMAN_TZ = ZoneInfo("Europe/Berlin")

def get_german_now() -> datetime:
    """Returns current datetime in German Local Time (Europe/Berlin, CET/CEST)."""
    return datetime.now(GERMAN_TZ)

def get_german_today_str() -> str:
    """Returns current German date as YYYY-MM-DD."""
    return datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")

def get_german_timestamp_str() -> str:
    """Returns current German timestamp as YYYY-MM-DD HH:MM:SS."""
    return datetime.now(GERMAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
