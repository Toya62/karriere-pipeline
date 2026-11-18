"""Unified Deduplication Core Engine for Karriere-Pipeline.

Consolidates cross-portal entity normalization, URL canonicalization,
location key extraction, requisition code discovery, and multi-tier
job deduplication across CSV, Database, and Catalog layers.
"""

from __future__ import annotations

import csv
import re
import urllib.parse
from typing import Any, Iterable

import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 1. URL Canonicalization
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"^\[([^\]]*)\]\(([^)]+)\)$")

_TRACKING_PREFIXES = (
    "utm_", "ref", "source", "trk", "tracking", "fbclid", "gclid",
    "urlhash", "refid", "trackingid", "origin", "midtoken", "eid",
    "_hsenc", "_hsmi", "mc_cid", "mc_eid", "ot", "si", "spm",
)

_TRACKING_EXACT = {
    "ref", "source", "trk", "src", "refid", "trackingid", "origin", "client",
    "context", "sender", "feature", "ved", "ei", "sei", "cv_source",
    "position", "seat", "page", "currentjobid", "job_id",
}

# Vital job IDs in query strings that MUST be preserved for identification
_PRESERVED_ID_PARAMS = {
    "id", "jid", "gh_jid", "req_id", "jobid", "requisition", "opening",
}


def plain_url(value: Any) -> str:
    """Extract plain URL string if wrapped in markdown [label](url)."""
    if not isinstance(value, str):
        return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    val = value.strip()
    m = _MD_LINK_RE.match(val)
    return m.group(2).strip() if m else val


def canonical_job_url(raw_url: Any) -> str:
    """Canonicalize job URL:
    - Strips markdown link formatting
    - Normalizes scheme and host (e.g. boards.greenhouse.io, myworkdayjobs.com)
    - Strips marketing/tracking query parameters (utm_*, ref, source, trk, etc.)
    - Preserves job identifier query parameters (gh_jid, id, jid, etc.)
    - Strips trailing ATS apply subpaths (/apply, /applyManually, etc.)
    - Normalizes commas and removes trailing slashes
    - Deterministically sorts remaining query parameters
    """
    url = plain_url(raw_url)
    if not url:
        return ""
    try:
        p = urllib.parse.urlparse(url.strip())
        if not p.scheme or not p.netloc:
            clean_str = url.strip().rstrip("/")
            return re.sub(r"/apply(?:/[^/]+)*$", "", clean_str, flags=re.IGNORECASE)

        netloc = p.netloc.lower()
        if netloc == "job-boards.greenhouse.io":
            netloc = "boards.greenhouse.io"
        elif "myworkdayjobs.com" in netloc:
            netloc = re.sub(r"\.wd\d+\.myworkdayjobs\.com$", ".myworkdayjobs.com", netloc)

        # Filter query params
        qs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        filtered_qs: list[tuple[str, str]] = []
        for k, v in qs:
            k_lower = k.lower()
            if k_lower in _PRESERVED_ID_PARAMS:
                filtered_qs.append((k, v))
                continue
            if any(k_lower.startswith(pref) for pref in _TRACKING_PREFIXES) or k_lower in _TRACKING_EXACT:
                continue
            filtered_qs.append((k, v))
        filtered_qs.sort()
        new_query = urllib.parse.urlencode(filtered_qs)

        norm_path = urllib.parse.unquote(p.path).rstrip("/")
        # Strip trailing ATS apply subpaths
        norm_path = re.sub(r"/apply(?:/[^/]+)*$", "", norm_path, flags=re.IGNORECASE)
        norm_path = re.sub(r"(?:%2C|,)+-?", "-", norm_path)

        return urllib.parse.urlunparse((p.scheme.lower(), netloc, norm_path, "", new_query, ""))
    except Exception:
        return url.strip().rstrip("/")


# ---------------------------------------------------------------------------
# 2. Company Normalization (Fix Bug 1 & 5)
# ---------------------------------------------------------------------------

_COMPANY_LEGAL_SUFFIXES_RE = re.compile(
    r"\b("
    r"(?:gmbh|ag)\s*&\s*co(?:\.\s*(?:kg|ohg|kgaa))?|"
    r"&\s*co(?:\.\s*(?:kg|ohg|kgaa))?|"
    r"gmbh\s*&\s*co(?:\.\s*kg|\s*ohg|\s*kgaa)?|"
    r"gmbh|"
    r"ag|"
    r"kgaa|"
    r"ug\s*\(?haftungsbeschr[äa]nkt\)?|"
    r"ug|"
    r"se|"
    r"inc(?:\.|\b)|"
    r"corp(?:\.|\b)|"
    r"corporation|"
    r"ltd(?:\.|\b)|"
    r"limited|"
    r"llc(?:\.|\b)|"
    r"plc(?:\.|\b)|"
    r"s\.?a\.?s?\.?|"
    r"s\.?r\.?l\.?|"
    r"e\.?v\.?|"
    r"ohg|"
    r"partg(?:mbba)?|"
    r"co\.?\s*kg|"
    r"kg|"
    r"co"
    r")\b",
    re.IGNORECASE,
)

_COMPANY_BRANCH_NOISE_RE = re.compile(
    r"\b(?:hauptsitz|niederlassung|standort|dienstsitz)\b.*$",
    re.IGNORECASE,
)


def normalize_company_entity(s: Any, strict: bool = False) -> str:
    """Canonical company normalization for cross-portal deduplication.

    In canonical mode (strict=False):
    - Strips parenthetical annotations: (Destatis), (Hauptsitz Berlin), (Europe)
    - Strips legal entity suffixes ONLY (GmbH, AG, SE, KG, Inc, Ltd, etc.)
    - PRESERVES corporate words: 'Systems', 'Technologies', 'Solutions', 'Services', 'Group'
      to prevent false-positive collapsing of distinct businesses (Fix Bug 1).
    - Strips branch suffix trailers like 'Hauptsitz Berlin', 'Dienstsitz Aurich'.

    In strict mode (strict=True):
    - Retains legal suffixes with only whitespace and basic non-alphanumeric chars cleaned.
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    text = str(s).strip()
    if not text:
        return ""

    if strict:
        return " ".join(re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", " ", text).lower().split())

    # Strip parenthetical annotations: (Destatis), (Hauptsitz ...), etc.
    text = re.sub(r"\(.*?\)", " ", text)
    # Strip branch trailer: 'Dienstsitz Aurich', 'Hauptsitz Frankfurt'
    text = _COMPANY_BRANCH_NOISE_RE.sub(" ", text)
    # Strip legal entity suffixes only (NOT 'solutions', 'systems', 'group', etc.)
    clean = _COMPANY_LEGAL_SUFFIXES_RE.sub(" ", text)
    # Non-alphanumeric to spaces
    clean = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", " ", clean).lower()
    tokens = clean.split()
    if tokens:
        return " ".join(tokens)

    # Fallback if entire company was stripped by legal form regex
    fallback = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", " ", str(s)).lower()
    return " ".join(fallback.split())


# ---------------------------------------------------------------------------
# 3. Title Normalization & Synonym Mapping (Fix Bug 4)
# ---------------------------------------------------------------------------

_GENDER_ANNOTATIONS_RE = re.compile(
    r"[\(\[\{/\-]\s*(?:"
    r"all\s+genders?|gn|geschlechtsneutral|divers|"
    r"[mwdfx](?:[\/\-\|\s]+[mwdfx])+|"
    r"m\/w\/d|f\/m\/d|m\/f\/d|w\/m\/d|d\/w\/m|m\/w\/x|w\/m\/x|f\/m\/x|"
    r"mwd|wmd|mfd"
    r")\s*[\)\]\}]|"
    r"\b(?:all\s+genders?|gn|geschlechtsneutral|m\/w\/d|f\/m\/d|m\/f\/d|w\/m\/d|d\/w\/m|m\/w\/x|w\/m\/x|f\/m\/x|mwd|wmd|mfd)\b",
    re.IGNORECASE,
)

_TITLE_COMPOUNDS: list[tuple[str, str]] = [
    (r"\bsoftwareentwickler(?:in)?\b", "software developer"),
    (r"\bsoftwareingenieur(?:in)?\b", "software engineer"),
    (r"\bbackend-?entwickler(?:in)?\b", "backend developer"),
    (r"\bfrontend-?entwickler(?:in)?\b", "frontend developer"),
    (r"\bfullstack-?entwickler(?:in)?\b", "fullstack developer"),
    (r"\bweb-?entwickler(?:in)?\b", "web developer"),
    (r"\bdateningenieur(?:in)?\b", "data engineer"),
    (r"\bdatenanalyst(?:in)?\b", "data analyst"),
    (r"\bsystem-?administrator(?:in)?\b", "system administrator"),
    (r"\bdevops-?ingenieur(?:in)?\b", "devops engineer"),
    (r"\bcloud-?ingenieur(?:in)?\b", "cloud engineer"),
    (r"\bwissenschaftliche[rn]?\s+mitarbeiter(?:in)?\b", "research associate"),
]

_ROLE_SYNONYMS: dict[str, str] = {
    "entwickler": "developer",
    "entwicklerin": "developer",
    "ingenieur": "engineer",
    "ingenieurin": "engineer",
}


def normalize_title_entity(
    s: Any,
    apply_synonyms: bool = True,
    synonymize_dev_eng: bool = True,
) -> str:
    """Canonical title normalization for cross-portal deduplication.

    - Strips gender markers: (m/w/d), [all genders], gn, etc.
    - Expands and normalizes German compound job roles (Softwareentwickler -> software developer)
    - If synonymize_dev_eng=True, maps developer ↔ engineer ↔ entwickler for cross-language dedup.
    - Strips trailing punctuation, brackets, dashes.
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    text = str(s).strip()
    if not text:
        return ""

    # 1. Strip gender markers
    clean = _GENDER_ANNOTATIONS_RE.sub(" ", text)
    clean = clean.lower()

    # 2. Compound expansion
    if apply_synonyms:
        for pattern, replacement in _TITLE_COMPOUNDS:
            clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)

    # 3. Strip trailing dashes or slashes
    clean = re.sub(r"[-–—\/]+$", "", clean).strip()

    # 4. Clean non-alphanumeric characters to space
    clean = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", " ", clean)
    tokens = clean.split()

    if apply_synonyms:
        mapped_tokens = []
        for t in tokens:
            syn = _ROLE_SYNONYMS.get(t, t)
            if synonymize_dev_eng and syn in ("engineer", "developer"):
                syn = "developer"
            mapped_tokens.append(syn)
        tokens = mapped_tokens

    return " ".join(tokens)


# ---------------------------------------------------------------------------
# 4. Location Extraction (Fix Bug 6)
# ---------------------------------------------------------------------------

_PLZ_RE = re.compile(r"\b(\d{5})\b")

_STREET_RE = re.compile(
    r"\b(?:str\.|straße|strasse|allee|platz|weg|ring|gasse|chaussee|damm|ufer|landstraße|pfad)\b|\b\d+[a-z]?\b",
    re.IGNORECASE,
)

_GEO_BOILERPLATE = {
    "deutschland", "germany", "bundesweit", "germany wide", "remote",
    "homeoffice", "home-office", "hybrid", "vor ort", "on-site", "flexibel", "standort",
    "baden-württemberg", "baden-wuerttemberg", "bayern", "bavaria",
    "brandenburg", "hessen", "hesse", "mecklenburg-vorpommern",
    "niedersachsen", "lower saxony", "nordrhein-westfalen", "north rhine-westphalia",
    "nrw", "rheinland-pfalz", "rhineland-palatinate", "saarland",
    "sachsen", "saxony", "sachsen-anhalt", "schleswig-holstein",
    "thüringen", "thuringia",
}


def extract_location_tokens(location: Any) -> set[str]:
    """Extracts all normalized location identifiers (PLZ and city names)."""
    if location is None or (isinstance(location, float) and pd.isna(location)):
        return set()
    s = str(location).strip()
    if not s:
        return set()

    keys: set[str] = set()
    # 1. 5-digit German PLZ match
    m = _PLZ_RE.search(s)
    if m:
        keys.add(m.group(1))
        # Remove PLZ for subsequent city token extraction
        s = _PLZ_RE.sub(" ", s)

    # 2. Split into segments by comma, slash, semicolon, pipe
    segments = [seg.strip() for seg in re.split(r"[,/|;]", s) if seg.strip()]
    for seg in segments:
        seg_lower = seg.lower().strip()
        if seg_lower in _GEO_BOILERPLATE:
            continue
        if _STREET_RE.search(seg_lower):
            continue
        cleaned = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß\s\-]", "", seg).strip().lower()
        if cleaned and len(cleaned) >= 2:
            keys.add(cleaned)

    return keys


def extract_location_key(location: Any) -> str:
    """Extracts normalized primary location identifier (prefers city name, falls back to PLZ).

    Avoids Bug 6 where splitting by comma returned street names instead of city.
    """
    tokens = extract_location_tokens(location)
    if not tokens:
        return ""
    # Prefer city name over PLZ
    cities = [t for t in tokens if not t.isdigit()]
    if cities:
        return cities[0]
    plzs = [t for t in tokens if t.isdigit()]
    if plzs:
        return plzs[0]
    return ""


# ---------------------------------------------------------------------------
# 5. Title Tokens & Jaccard Similarity (Fix Bug 3 & 4)
# ---------------------------------------------------------------------------

_TITLE_STOPWORDS = {
    "im", "bereich", "für", "fuer", "und", "von", "in", "m", "w", "d",
    "mitarbeiterin", "mitarbeiter", "wissenschaftliche", "wissenschaftlicher",
}


def extract_title_tokens(title: Any, apply_synonyms: bool = True) -> set[str]:
    """Extract substantive semantic keyword tokens from a job title.
    Preserves meaningful short tokens like ai, ml, qa, bi, go, ii, iii.
    """
    if title is None or (isinstance(title, float) and pd.isna(title)):
        return set()
    cleaned = normalize_title_entity(str(title), apply_synonyms=apply_synonyms, synonymize_dev_eng=True)
    return {
        w for w in cleaned.split()
        if len(w) >= 2 and w not in _TITLE_STOPWORDS
    }


def compute_jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity index between two token sets."""
    if not set_a or not set_b:
        return 0.0
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return len(set_a & set_b) / union


# ---------------------------------------------------------------------------
# 6. Requisition ID & Description Fingerprint
# ---------------------------------------------------------------------------

_REQ_ID_RE = re.compile(
    r"(?:referenzcode|kennziffer|referenznummer|stellennummer|referenz-nr\.?)[^0-9\n]{0,50}?([0-9]{4,}[-_][0-9]{2,})",
    re.IGNORECASE,
)


def extract_req_id(desc: Any) -> str | None:
    """Extracts base requisition/reference code from job description text."""
    if not desc or not isinstance(desc, str):
        return None
    clean = desc.replace("\\", "")
    m = _REQ_ID_RE.search(clean)
    if m:
        full_code = m.group(1)
        base = full_code.split("_")[0].split("-")[0]
        return base if len(base) >= 4 else None
    return None


def desc_fingerprint(desc: Any) -> str:
    """Generates fingerprint from description by extracting character sequences."""
    if not desc or not isinstance(desc, str):
        return ""
    clean = re.sub(r"[^a-zA-Z0-9]+", "", str(desc).lower())
    return clean[:300]


# ---------------------------------------------------------------------------
# 7. In-Memory Job Dedup Index (For DB & Scrapers)
# ---------------------------------------------------------------------------

class JobDedupIndex:
    """High-performance in-memory index for deduplication.

    Supports:
    1. Canonical URL lookup (O(1))
    2. Canonical Entity key lookup: company_norm ||| title_norm (O(1))
    3. Requisition ID lookup (O(1))
    4. Location + Title token Jaccard fuzzy match (>= threshold)
    """

    def __init__(self, similarity_threshold: float = 0.80):
        self.similarity_threshold = similarity_threshold
        # canonical_url -> (job_id, raw_url, desc_len)
        self.url_map: dict[str, tuple[int, str, int]] = {}
        # entity_key -> (job_id, raw_url, desc_len)
        self.entity_map: dict[str, tuple[int, str, int]] = {}
        # req_id -> (job_id, raw_url, desc_len)
        self.req_map: dict[str, tuple[int, str, int]] = {}
        # list of (loc_tokens, title_tokens, job_id, raw_url, desc_len, comp_norm)
        self.fuzzy_records: list[tuple[set[str], set[str], int, str, int, str]] = []

    def add(
        self,
        job_id: int,
        url: str,
        company: str,
        title: str,
        location: str = "",
        desc: str = "",
        desc_len: int | None = None,
    ) -> None:
        """Register job record in the dedup index."""
        actual_desc_len = desc_len if desc_len is not None else len(desc or "")
        canon_url = canonical_job_url(url)
        if canon_url:
            self.url_map[canon_url] = (job_id, url, actual_desc_len)

        c_norm = normalize_company_entity(company)
        t_norm = normalize_title_entity(title)
        if c_norm and t_norm:
            self.entity_map[f"{c_norm}|||{t_norm}"] = (job_id, url, actual_desc_len)

        req_id = extract_req_id(desc)
        if req_id:
            self.req_map[req_id] = (job_id, url, actual_desc_len)

        loc_tokens = extract_location_tokens(location)
        t_tokens = extract_title_tokens(title)
        if loc_tokens and len(t_tokens) >= 2:
            self.fuzzy_records.append((loc_tokens, t_tokens, job_id, url, actual_desc_len, c_norm))

    def find_duplicate(
        self,
        url: str,
        company: str,
        title: str,
        location: str = "",
        desc: str = "",
    ) -> tuple[int, str, int] | None:
        """Find matching existing duplicate job."""
        # 1. Canonical URL
        canon_url = canonical_job_url(url)
        if canon_url and canon_url in self.url_map:
            return self.url_map[canon_url]

        # 2. Canonical Entity Key
        c_norm = normalize_company_entity(company)
        t_norm = normalize_title_entity(title)
        if c_norm and t_norm:
            k = f"{c_norm}|||{t_norm}"
            if k in self.entity_map:
                return self.entity_map[k]

        # 3. Requisition ID
        req_id = extract_req_id(desc)
        if req_id and req_id in self.req_map:
            return self.req_map[req_id]

        # 4. Location + Title Token Jaccard Fuzzy Overlap
        loc_tokens = extract_location_tokens(location)
        t_tokens = extract_title_tokens(title)
        if loc_tokens and len(t_tokens) >= 2:
            for s_loc_tokens, s_tokens, s_id, s_url, s_desc_len, s_comp in self.fuzzy_records:
                if loc_tokens & s_loc_tokens:  # Shared city or PLZ
                    sim = compute_jaccard_similarity(t_tokens, s_tokens)
                    c_match = bool(c_norm and s_comp and (c_norm == s_comp or c_norm in s_comp or s_comp in c_norm))
                    if (c_match and sim >= self.similarity_threshold) or (sim >= 0.80 and len(t_tokens) >= 3):
                        return (s_id, s_url, s_desc_len)

        return None

    @classmethod
    def from_cursor(cls, cursor: Any, similarity_threshold: float = 0.80) -> "JobDedupIndex":
        """Build JobDedupIndex from DB cursor efficiently."""
        index = cls(similarity_threshold=similarity_threshold)
        cursor.execute(
            "SELECT id, company, title, url, location, LENGTH(COALESCE(description, '')), "
            "SUBSTR(COALESCE(description, ''), 1, 2000) FROM jobs"
        )
        for j_id, j_comp, j_title, j_url, j_loc, j_desc_len, j_desc_excerpt in cursor.fetchall():
            index.add(
                job_id=j_id,
                url=j_url or "",
                company=j_comp or "",
                title=j_title or "",
                location=j_loc or "",
                desc=j_desc_excerpt or "",
                desc_len=int(j_desc_len or 0),
            )
        return index


# ---------------------------------------------------------------------------
# 8. Unified DataFrame Deduplication (Fix Bug 7)
# ---------------------------------------------------------------------------

def dedup_job_dataframe(
    df: pd.DataFrame,
    keep_longest_desc: bool = False,
    similarity_threshold: float = 0.75,
) -> pd.DataFrame:
    """Unified 5-tier deduplication for job DataFrames:
    1. Canonical URL
    2. Requisition ID from description
    3. Canonical Entity Key (company_entity + title_entity)
    4. Exact lowercase title + company
    5. Location + Title-token Jaccard similarity >= threshold

    If keep_longest_desc is True, sorts rows so richest description is retained.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    df = df.copy()
    before = len(df)

    if keep_longest_desc and "description" in df.columns:
        desc_lens = df["description"].fillna("").astype(str).str.len()
        df = df.iloc[desc_lens.argsort()[::-1]].reset_index(drop=True)

    # Tier 1: Canonical URL
    url_col = next((c for c in ("job_url", "url", "link") if c in df.columns), None)
    if url_col:
        df["_canon_url"] = df[url_col].apply(canonical_job_url)
        valid_urls = df["_canon_url"] != ""
        if valid_urls.any():
            df_u = df[valid_urls].drop_duplicates(subset=["_canon_url"], keep="first")
            df = pd.concat([df_u, df[~valid_urls]], ignore_index=True)
        df = df.drop(columns=["_canon_url"], errors="ignore")

    # Tier 2: Requisition ID
    if "description" in df.columns and len(df) > 1:
        df["_req_id"] = df["description"].apply(extract_req_id)
        valid_reqs = df["_req_id"].notna() & (df["_req_id"] != "")
        if valid_reqs.any():
            df_r = df[valid_reqs].drop_duplicates(subset=["_req_id"], keep="first")
            df = pd.concat([df_r, df[~valid_reqs]], ignore_index=True)
        df = df.drop(columns=["_req_id"], errors="ignore")

    # Tier 3 & 4: Canonical Entity Key & Exact Fallback
    comp_col = "company" if "company" in df.columns else None
    title_col = "title" if "title" in df.columns else None
    if comp_col and title_col and len(df) > 1:
        df["_entity_key"] = (
            df[comp_col].apply(normalize_company_entity)
            + "|||"
            + df[title_col].apply(normalize_title_entity)
        )
        valid_keys = (
            (df["_entity_key"] != "|||")
            & (~df["_entity_key"].str.startswith("|||"))
            & (~df["_entity_key"].str.endswith("|||"))
        )
        if valid_keys.any():
            df_k = df[valid_keys].drop_duplicates(subset=["_entity_key"], keep="first")
            df = pd.concat([df_k, df[~valid_keys]], ignore_index=True)
        df = df.drop(columns=["_entity_key"], errors="ignore")

        # Tier 4: Exact fallback
        df["_raw_key"] = (
            df[title_col].fillna("").astype(str).str.lower().str.strip()
            + "|||"
            + df[comp_col].fillna("").astype(str).str.lower().str.strip()
        )
        df = df.drop_duplicates(subset=["_raw_key"], keep="first").drop(columns=["_raw_key"], errors="ignore")

    # Tier 5: Location + Title-token Jaccard Fuzzy Overlap
    loc_col = "location" if "location" in df.columns else None
    if loc_col and title_col and len(df) > 1:
        keep_indices: list[int] = []
        seen_loc_tokens: list[tuple[set[str], set[str], str]] = []
        for idx, row in df.iterrows():
            loc_tokens = extract_location_tokens(row.get(loc_col, ""))
            t_tokens = extract_title_tokens(row.get(title_col, ""))
            c_norm = normalize_company_entity(row.get(comp_col, "")) if comp_col else ""
            if not loc_tokens or len(t_tokens) < 2:
                keep_indices.append(idx)
                continue
            is_dup = False
            for s_loc_tokens, s_tokens, s_comp in seen_loc_tokens:
                if loc_tokens & s_loc_tokens:  # Shared city or PLZ
                    sim = compute_jaccard_similarity(t_tokens, s_tokens)
                    c_match = bool(c_norm and s_comp and (c_norm == s_comp or c_norm in s_comp or s_comp in c_norm))
                    if (c_match and sim >= similarity_threshold) or (sim >= 0.80 and len(t_tokens) >= 3):
                        is_dup = True
                        break
            if not is_dup:
                seen_loc_tokens.append((loc_tokens, t_tokens, c_norm))
                keep_indices.append(idx)
        df = df.loc[keep_indices]

    df = df.reset_index(drop=True)
    logger.info(f"  Dedup:              {before} -> {len(df)} ({before - len(df)} duplicates removed)")
    return df
