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


def _normalize_company(s: str) -> str:
    s = str(s).lower().strip()
    s = re.sub(r"\b(gmbh|ag|co|kg|se|inc|corp|ltd|s\.a\.|university|universität|uni|hochschule)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "-")


def _has_desc(d: str) -> bool:
    return bool(str(d).strip())

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
