import os
"""
filters.py  —  All regex patterns and filter functions

All keyword lists are loaded from filter_config.yml (falls back to
filter_config.example.yml). The Python code is a pure regex-builder —
no technology knowledge is hardcoded here.
"""

import re
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.config import MAX_DAYS, CROSS_REPOST_DAYS, MAX_APPLICANTS, REJECT_JOB_TYPES
from src.core.config import (
    REJECT_TECHNOLOGIES, GERMAN_MIN_LEVEL,
    SENIOR_TITLE_KEYWORDS, SENIOR_LEVEL_SET,
    NOISE_TITLE_KEYWORDS, FORBIDDEN_TECH_SOFT, FORBIDDEN_TECH_HARD,
    CORE_TARGET_KEYWORDS, CS_RELEVANCE_KEYWORDS, NON_CS_RESEARCH_KEYWORDS,
    AGGREGATOR_COMPANIES, REJECT_EMPLOYMENT_TYPES,
)
from src.core.logger import get_logger
logger = get_logger(__name__)


def _kw_pat(*keyword_lists, word_boundary: bool = True) -> re.Pattern:
    """Build a compiled regex OR-pattern from one or more keyword lists.

    Terms that start or end with non-word characters (e.g. '.net', 'c#')
    use lookaround assertions instead of \\b which doesn't work on them.
    """
    all_terms = [kw for lst in keyword_lists for kw in lst if kw]
    if not all_terms:
        return re.compile(r"(?!x)x")  # never-match

    parts = []
    for kw in all_terms:
        esc = re.escape(kw)
        if not word_boundary:
            parts.append(esc)
        elif not kw[0].isalnum() and kw[0] != "_":
            # starts with special char (e.g. '.net') — use negative lookbehind
            parts.append(rf"(?<![a-zA-Z0-9]){esc}(?![a-zA-Z0-9])")
        elif not kw[-1].isalnum() and kw[-1] != "_":
            # ends with special char (e.g. 'c#') — use negative lookahead
            parts.append(rf"\b{esc}(?![a-zA-Z0-9])")
        else:
            parts.append(rf"\b{esc}\b")

    pattern = "(?:" + "|".join(parts) + ")"
    return re.compile(pattern, re.IGNORECASE)


# ── Seniority patterns (built from filter_config.yml) ────────────────────────
SENIOR_TITLE_PAT = _kw_pat(SENIOR_TITLE_KEYWORDS)

# SENIOR_DESC_PAT anchors to explicit hiring verbs — structural regex, stays as code.

# ── SENIOR_DESC_PAT: only fires when the description is *actively seeking*
#    a senior person for THIS role.  Does NOT fire on:
#      - "unser Senior-Team freut sich …"           (describing existing team)
#      - "Sie arbeiten neben Senior Engineers …"    (describing colleagues)
#      - "requires strong experience"               (too generic, fires on all DE JDs)
#      - "senior (engineer|developer|…)" bare noun  (any mention of the word)
#
#    Anchored to explicit hiring verbs in both DE and EN.
SENIOR_DESC_PAT = re.compile(
    r"("
    # German hiring verbs + senior
    r"suchen\s+(wir\s+)?(einen?\s+)?(erfahrenen?\s+)?senior"
    r"|wir\s+(suchen|bieten|stellen\s+ein).{0,40}senior"
    r"|stelle\s+f[üu]r\s+(einen?\s+)?senior"
    # English hiring verbs + senior
    r"|we\s+(are\s+)?(looking\s+for|seeking|hiring)\s+a\s+senior"
    r"|looking\s+for\s+a\s+senior"
    r"|seeking\s+a\s+senior"
    r"|experience\s+(at\s+a\s+)?senior\s+level|senior[\s-]level\s+experience"
    # Explicit year thresholds that unambiguously signal seniority
    r"|minimum\s+[5-9]\+?\s*years|mindestens\s+[5-9]\+?\s*jahre|bring(st)?\s+[5-9]\+?\s*jahre|bring(st)?\s+[5-9]\+?\s*years|(?<!\d-)(?<!\d\s)\b[5-9]\+?\s*jahre?\s+erfahrung|(?<!\d-)(?<!\d\s)\b[5-9]\+?\s*years?\s+(of\s+)?experience"
    # Architect / Expert / Team Lead level description requirements
    r"|langj\u00e4hrige.{0,20}architektur|mehrj\u00e4hrige.{0,20}architektur|expert.{0,15}forensik"
    r"|lead\s+(and\s+mentor\s+)?(a\s+)?team|f\u00fchrungskraft|f\u00fchrungsverantwortung"
    r")",
    re.IGNORECASE,
)

SENIOR_LEVEL_VALUES = SENIOR_LEVEL_SET

JUNIOR_PAT = re.compile(
    r"\b(junior|jr\.?|entry.?level|berufseinsteiger|einsteiger|graduate"
    r"|werkstudent|trainee|intern|praktikant|young\s+professional|absolvent|fresh\s+grad)\b",
    re.IGNORECASE,
)
RESEARCH_ROLE_PAT = re.compile(
    r"(wissenschaftlich|research\s+(associate|engineer|fellow|assistant)"
    r"|doktorand|phd\s+(student|candidate)|forschungsingenieur|postdoc|post.doc)",
    re.IGNORECASE,
)
NON_FULLTIME_TITLE_PAT = re.compile(
    r"\b(werkstudent(?:in)?|working\s+student|intern\b|internship|praktikant(?:in)?|masterstudent(?:in)?|bachelorstudent(?:in)?"
    r"|praktikum|trainee|apprenti|ausbildung|azubi|dual\s+student"
    r"|duales\s+studium|student\s+assistant|studentische\s+hilfskraft"
    # match both 'studentischer mitarbeiter' (person) AND 'studentische mitarbeit' (activity noun)
    r"|studentische[rs]?\s+mitarbeiter|studentische\s+mitarbeit"
    r"|thesisverfasser|thesis\s+student"
    r"|abschlussarbeit|bachelor\s*arbeit|master\s*arbeit"
    # Bug 3 fix: English PhD/research roles were not caught
    r"|doctoral\b|dissertation\b|research\s+associate\b"
    r"|phd\s+(position|role|fellowship|scholarship)|interim\b|freelance\b|freiberuflich\b)\b",
    re.IGNORECASE,
)
# ── CS relevance pattern (built from filter_config.yml) ──────────────────────
CS_KEYWORD_PAT = _kw_pat(CS_RELEVANCE_KEYWORDS)

HIGH_EXP_PATTERNS = [
    r"[7-9]\+\s*years?", r"10\+\s*years?",
    r"(at\s+least|minimum|more\s+than|over|min\.?)\s*[7-9]\s*years?",
    r"(at\s+least|minimum|more\s+than|over|min\.?)\s*10\s*years?",
    r"[7-9]\+\s*jahre", r"10\+\s*jahre",
    r"(mindestens|mehr\s+als|\u00fcber|min\.?)\s*[7-9]\s*jahre",
    r"(mindestens|mehr\s+als|\u00fcber|min\.?)\s*10\s*jahre",
    r"(seven|eight|nine|ten)\s+(or\s+more\s+)?years?\s+(of\s+)?(professional\s+)?experience",
    r"[5-9]\s*(to|-|\u2013|bis)\s*1[0-9]\s*years?",
    r"[5-9]\s*(to|-|\u2013|bis)\s*1[0-9]\s*jahre",
]

# ── Language filter patterns ──────────────────────────────────────────────────
ENGLISH_OK_PATTERNS = [
    r"english\s+(is\s+)?(sufficient|enough|required|mandatory|accepted|welcome)",
    r"working\s+language.{0,20}english",
    r"englisch.{0,20}(ausreichend|gen\u00fcgt|akzeptiert|willkommen)",
    r"sprache.{0,20}englisch",
    r"international.{0,20}team",
    r"english.{0,10}(b2|c1|c2)",
    r"(b2|c1|c2).{0,10}english",
    r"oder\s+englisch",
    r"or\s+english",
    r"gute\s+englischkenntnisse",
    r"englischkenntnisse.{0,30}(von\s+vorteil|w\u00fcnschenswert|hilfreich|ausreichend|gen\u00fcgen)",
    r"englisch.{0,20}(b1|b2|c1|kenntnisse|vorteil)",
    r"(b1|b2|c1).{0,10}englisch",
    r"english\s+(language\s+)?(skills?\s+)?(are\s+)?(an?\s+)?(advantage|preferred|welcome|plus|sufficient|ok)",
    r"communication\s+(in\s+)?english",
    r"arbeitssprache.{0,20}englisch",
    r"business\s+english",
    r"englisch\s+(ist\s+)?(ausreichend|reicht|gen\u00fcgt|willkommen|ok)",
    r"english\s+first",
    r"primarily\s+english",
    r"mainly\s+english",
    r"our\s+(team\s+)?language\s+is\s+english",
    r"we\s+(work|communicate|speak)\s+(in\s+)?english",
    r"english\s+speaking\s+(team|environment|company|workplace)",
    r"no\s+german\s+(required|needed|necessary)",
    r"german\s+(is\s+)?(not\s+required|not\s+needed|not\s+necessary|a\s+plus|optional|nice\s+to\s+have)",
    r"deutsch\s+(ist\s+)?nicht\s+(erforderlich|notwendig|zwingend|vorausgesetzt)",
]
GERMAN_SOFT_PATTERNS = [
    r"deutsch.{0,20}(b1|b2|grundkenntnisse|gute\s+kenntnisse|von\s+vorteil|w\u00fcnschenswert|hilfreich)",
    r"(b1|b2).{0,20}deutsch",
    r"grundlegende.{0,15}deutsch",
    r"deutsch.{0,20}nicht\s+zwingend",
    r"sehr\s+gute.{0,15}deutsch.{0,30}(von\s+vorteil|w\u00fcnschenswert|hilfreich|nicht\s+zwingend)",
]

# ── German level gate: derived from GERMAN_MIN_LEVEL in user_profile.yml ────────
# Level order: A1 < A2 < B1 < B2 < C1 < C2 < NATIVE
# Patterns below reject any job requiring a level ABOVE the user's current level.
_LEVEL_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2", "NATIVE"]
_user_level_idx = _LEVEL_ORDER.index(GERMAN_MIN_LEVEL) if GERMAN_MIN_LEVEL in _LEVEL_ORDER else 3  # default B2
_reject_levels = _LEVEL_ORDER[_user_level_idx + 1:]  # levels above user's level

# Build hard German patterns from the levels that must be rejected
_c1c2_terms = "|".join(lv.lower() for lv in _reject_levels if lv not in ("NATIVE",))
_native_terms = "muttersprache|muttersprachlich" if "NATIVE" in _reject_levels else ""
_verhandlung = "verhandlungssicher" if "C1" in _reject_levels else ""

_hard_terms = "|".join(t for t in [_c1c2_terms, _native_terms, _verhandlung] if t)

if _hard_terms:
    GERMAN_HARD_PATTERNS = [
        rf"deutsch.{{0,50}}\b({_hard_terms})\b",
        rf"({_hard_terms}).{{0,15}}deutsch",
        r"muttersprach.{0,10}deutsch" if "NATIVE" in _reject_levels else r"(?!x)x",  # never-match placeholder
        r"verhandlungssicher.{0,20}deutsch" if "C1" in _reject_levels else r"(?!x)x",
        r"verhandlungssichere\s+deutschkenntnisse" if "C1" in _reject_levels else r"(?!x)x",
        r"interview.{0,20}deutsch" if "C1" in _reject_levels else r"(?!x)x",
        rf"deutsch\s+auf\s+({_hard_terms.replace('|', '|')})\s+niveau",
        rf"deutschkenntnisse\s+auf\s+({_hard_terms})\s+niveau",
        rf"sprachkenntnisse.{{0,15}}deutsch.{{0,20}}({_hard_terms})",
        r"pr\u00e4sentationssichere?\s+deutsch" if "C1" in _reject_levels else r"(?!x)x",
        rf"mindestens\s+({_c1c2_terms})" if _c1c2_terms else r"(?!x)x",
        rf"mind\.?\s+({_c1c2_terms})" if _c1c2_terms else r"(?!x)x",
        rf"(minimum|min\.?)\s+(level\s+)?({_c1c2_terms})" if _c1c2_terms else r"(?!x)x",
        rf"german.{{0,20}}({_c1c2_terms})" if _c1c2_terms else r"(?!x)x",
        rf"({_c1c2_terms}).{{0,20}}german" if _c1c2_terms else r"(?!x)x",
    ]
else:
    # User has native level — no German level is too high to reject
    GERMAN_HARD_PATTERNS = []

# ── Noise title gate (built from filter_config.yml) ─────────────────────────
NOISE_TITLE_PAT = _kw_pat(NOISE_TITLE_KEYWORDS)


# ── Forbidden tech gates (built from filter_config.yml + user_profile.yml) ──
FORBIDDEN_TECH_PAT = _kw_pat(FORBIDDEN_TECH_SOFT, REJECT_TECHNOLOGIES)
HARD_FORBIDDEN_TECH_PAT = _kw_pat(FORBIDDEN_TECH_HARD, REJECT_TECHNOLOGIES)

# ── Core target title gate (from filter_config.yml) ─────────────────────────
CS_CORE_TITLE_PAT = _kw_pat(CORE_TARGET_KEYWORDS, CS_RELEVANCE_KEYWORDS)

# ── Gender-suffix cleanup (BA titles always contain "(m/w/d)" variants) ───────
_GENDER_SUFFIX_RE = re.compile(
    r"\s*[\(\[]?\s*[mwfd][\s/\\|]+[mwfd][\s/\\|]+[mwfd]\s*[\)\]]?\s*"
    r"|\s*\(all genders?\)\s*"
    r"|\s*\(gn\)\s*",
    re.IGNORECASE,
)

_PAREN_SENIOR_RE = re.compile(
    r"\([\s\w/]*jr\.?/sr\.?[\s\w/]*\)"
    r"|\([\s\w/]*junior/senior[\s\w/]*\)",
    re.IGNORECASE,
)


def _clean_title(title: str) -> str:
    """Strip BA gender suffixes and optional junior/senior options before pattern matching."""
    cleaned = _GENDER_SUFFIX_RE.sub(" ", str(title))
    cleaned = re.sub(r"\((senior|sr\.?)\)", r" \1 ", cleaned, flags=re.IGNORECASE)
    cleaned = _PAREN_SENIOR_RE.sub(" ", cleaned)
    return " ".join(cleaned.split())



def _title_has_seniority_signal(title: str) -> bool:
    """True if the title itself carries a seniority word (senior/lead/etc.)."""
    return bool(SENIOR_TITLE_PAT.search(_clean_title(title)))


# ── Language helpers ──────────────────────────────────────────────────────────
def _has_hard_german(t: str) -> bool:
    return any(re.search(p, t, re.I) for p in GERMAN_HARD_PATTERNS)


def should_reject_language(text: str, is_research: bool = False) -> bool:
    t = text.lower() if text else ""
    return _has_hard_german(t)


# ── Internal helpers ──────────────────────────────────────────────────────────
def _has_desc(d: str) -> bool:
    return bool(str(d).strip())


def _lower(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.lower()


def _desc_fingerprint(desc: str) -> str:
    _WS_RE = re.compile(r"\s+")
    if not desc or not isinstance(desc, str):
        return ""
    return _WS_RE.sub(" ", desc.lower().strip())[:500]


# ── Filter functions ──────────────────────────────────────────────────────────
def filter_reposted(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    if before == 0:
        return df
    def _is_flagged(row) -> bool:
        lt = str(row.get("listing_type", "") or "").strip().lower()
        if "repost" in lt:
            return True
        ir = row.get("is_reposted", None)
        if ir is None or (isinstance(ir, float) and pd.isna(ir)):
            return False
        if isinstance(ir, bool):
            return ir
        return str(ir).strip().lower() in ("true", "1", "yes", "reposted")
    mask = ~pd.Series([_is_flagged(row) for _, row in df.iterrows()], index=df.index)
    logger.info(f"  Repost flag (L0):   {mask.sum():4d} / {before} kept  ({before - mask.sum()} removed)")
    return df[mask].copy().reset_index(drop=True)


def filter_reposts(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    if before == 0:
        return df
    df = df.copy()
    df["_fp"] = df.get("description", pd.Series("", index=df.index)).fillna("").apply(_desc_fingerprint)
    df["_cn"] = df.get("company",     pd.Series("", index=df.index)).fillna("").str.lower().str.strip()
    df["_rk"] = df.apply(lambda r: f"{r['_cn']}|||{r['_fp']}" if r["_fp"] else f"__nofp_{r.name}__", axis=1)
    if "date_posted" in df.columns:
        df = df.sort_values("date_posted", ascending=False, na_position="last",
                            key=lambda s: pd.to_datetime(s, utc=True, errors="coerce"))
    df = df.drop_duplicates(subset=["_rk"], keep="first").drop(columns=["_fp", "_cn", "_rk"])
    logger.info(f"  Repost (within):    {len(df):4d} / {before} kept  ({before - len(df)} removed)")
    return df.reset_index(drop=True)


def filter_seen_reposts(
    df: pd.DataFrame,
    all_time_files: "str | list[str] | None" = None,
    db_path: str = "data/karriere.db",
) -> pd.DataFrame:
    """
    Cross-run dedup by description fingerprint.
    Primary source of truth: SQLite data/karriere.db.
    """
    from src.core.utils import _normalize_company
    before = len(df)
    if before == 0:
        return df

    cutoff_cross = datetime.now(tz=timezone.utc) - timedelta(days=CROSS_REPOST_DAYS)
    cutoff_str = cutoff_cross.strftime("%Y-%m-%d")
    seen: set[str] = set()

    # 1. Primary: SQLite karriere.db
    if db_path and os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT company, description FROM jobs WHERE scraped_at >= ? OR scraped_at IS NULL OR scraped_at = ''",
                (cutoff_str,)
            )
            for c, d in cursor.fetchall():
                fp = _desc_fingerprint(str(d or "").strip())
                cn = _normalize_company(str(c or "").strip())
                if fp and cn:
                    seen.add(f"{cn}|||{fp}")
            conn.close()
        except Exception as exc:
            logger.warning(f"Could not load seen reposts from SQLite {db_path}: {exc}")

    # 2. Legacy fallback if all_time_files provided
    if all_time_files:
        if isinstance(all_time_files, str):
            all_time_files = [all_time_files]
        for all_time_file in all_time_files:
            try:
                existing = pd.read_csv(
                    all_time_file,
                    usecols=lambda c: c in ("company", "description", "first_seen", "date_posted"),
                )
            except (FileNotFoundError, ValueError):
                continue
            if existing.empty:
                continue
            existing["_fp"] = existing.get("description", pd.Series("", index=existing.index)).fillna("").apply(_desc_fingerprint)
            existing["_cn"] = existing.get("company",     pd.Series("", index=existing.index)).fillna("").apply(_normalize_company)
            for k in existing.apply(lambda r: f"{r['_cn']}|||{r['_fp']}" if r["_fp"] else "", axis=1):
                if k:
                    seen.add(k)

    if not seen:
        logger.info(f"  Repost (cross):     {before:4d} / {before} kept  (no entries in DB)")
        return df
    df = df.copy()
    df["_fp"] = df.get("description", pd.Series("", index=df.index)).fillna("").apply(_desc_fingerprint)
    df["_cn"] = df.get("company",     pd.Series("", index=df.index)).fillna("").apply(_normalize_company)
    df["_rk"] = df.apply(lambda r: f"{r['_cn']}|||{r['_fp']}" if r["_fp"] else "", axis=1)
    mask = df["_rk"].apply(lambda k: k == "" or k not in seen)
    df = df[mask].drop(columns=["_fp", "_cn", "_rk"])
    logger.info(f"  Repost (cross):     {len(df):4d} / {before} kept  ({before - len(df)} removed, window={CROSS_REPOST_DAYS}d)")
    return df.reset_index(drop=True)


def filter_seen_reposts_by_url(
    df: pd.DataFrame,
    all_time_files: "str | list[str] | None" = None,
    db_path: str = "data/karriere.db",
) -> pd.DataFrame:
    """
    Cross-run URL dedup.
    Primary source of truth: SQLite data/karriere.db.
    """
    from src.core.utils import _plain_url
    before = len(df)
    if before == 0:
        return df
    if "job_url" not in df.columns:
        logger.info(f"  Seen URL (cross):   {before:4d} / {before} kept  (no job_url column)")
        return df

    cutoff_cross = datetime.now(tz=timezone.utc) - timedelta(days=CROSS_REPOST_DAYS)
    cutoff_str = cutoff_cross.strftime("%Y-%m-%d")
    seen_urls: set[str] = set()

    # 1. Primary: SQLite karriere.db
    if db_path and os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT url FROM jobs WHERE description IS NOT NULL AND length(trim(description)) > 10 AND (scraped_at >= ? OR scraped_at IS NULL OR scraped_at = '')",
                (cutoff_str,)
            )
            for (u,) in cursor.fetchall():
                if u:
                    clean_u = _plain_url(str(u)).strip()
                    if clean_u:
                        seen_urls.add(clean_u)
            conn.close()
        except Exception as exc:
            logger.warning(f"Could not load seen URLs from SQLite {db_path}: {exc}")

    # 2. Legacy fallback if all_time_files provided
    if all_time_files:
        if isinstance(all_time_files, str):
            all_time_files = [all_time_files]
        for all_time_file in all_time_files:
            try:
                existing = pd.read_csv(
                    all_time_file,
                    usecols=lambda c: c in ("job_url", "description", "first_seen", "date_posted"),
                )
            except (FileNotFoundError, ValueError):
                continue
            if existing.empty:
                continue
            has_desc_mask = existing.get("description", pd.Series("", index=existing.index)).fillna("").str.strip().ne("")
            for u in existing[has_desc_mask]["job_url"].dropna().apply(_plain_url).str.strip():
                if u:
                    seen_urls.add(u)

    if not seen_urls:
        logger.info(f"  Seen URL (cross):   {before:4d} / {before} kept  (no entries in DB)")
        return df

    df = df.copy()
    mask = df["job_url"].apply(_plain_url).str.strip().apply(lambda u: u not in seen_urls)
    removed = int((~mask).sum())
    df = df[mask].reset_index(drop=True)
    logger.info(f"  Seen URL (cross):   {len(df):4d} / {before} kept  ({removed} removed)")
    return df


def filter_date(df: pd.DataFrame, max_days: int | None = None, is_linkedin: bool = False) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    from src.config import get_max_days
    if max_days is None:
        max_days = get_max_days()
    
    # Align cutoff to midnight UTC so date-only jobs (e.g. yesterday) are not dropped
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=max_days)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    def recent(row) -> bool:
        for col in ("date_posted", "first_seen", "scraped_at"):
            v = row.get(col, "")
            s = str(v).strip() if v is not None else ""
            if s and s.lower() not in ("nan", "none", "nat", "", "invalid"):
                try:
                    dt = pd.to_datetime(s, utc=True, errors="coerce")
                    if not pd.isna(dt):
                        return dt >= cutoff
                except Exception:
                    pass
        return True

    mask = df.apply(recent, axis=1)
    logger.info(f"  Date filter ({max_days}d cutoff): {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Date filter")
    return df[mask].copy()


def _log_removed(df: pd.DataFrame, mask: pd.Series, filter_name: str, portal: str = None) -> None:
    try:
        removed_df = df[~mask].copy()
        if removed_df.empty:
            return

        for _, row in removed_df.iterrows():
            title = str(row.get("title", ""))[:65]
            company = str(row.get("company", ""))[:40]
            url = str(row.get("job_url", ""))
            logger.debug(f"    ❌ [{filter_name}] Filtered out: '{title}' @ {company}")
            if url and url.lower() not in ("nan", "none", ""):
                logger.debug(f"       Link: {url}")
    except Exception as exc:
        logger.debug(f"Could not log removed rows for {filter_name}: {exc}")


def filter_seniority(df: pd.DataFrame) -> pd.DataFrame:
    title_col = df.get("title",       pd.Series("", index=df.index)).fillna("")
    desc_col  = df.get("description", pd.Series("", index=df.index)).fillna("")
    level_col = _lower(df.get("job_level", df.get("seniority_level", pd.Series("", index=df.index))))

    def reject(title, desc, level) -> bool:
        clean = _clean_title(str(title))
        if JUNIOR_PAT.search(clean) or RESEARCH_ROLE_PAT.search(clean):
            return False
        if level.strip() in SENIOR_LEVEL_VALUES:
            return True
        if SENIOR_TITLE_PAT.search(clean):
            return True
        if _has_desc(desc) and SENIOR_DESC_PAT.search(str(desc)):
            return True
        return False

    mask = ~pd.Series(
        [reject(t, d, lv) for t, d, lv in zip(title_col, desc_col, level_col)],
        index=df.index,
    )
    logger.info(f"  Seniority filter:   {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Seniority filter")
    return df[mask].copy()


def filter_experience(df: pd.DataFrame) -> pd.DataFrame:
    pat = re.compile("|".join(HIGH_EXP_PATTERNS), re.IGNORECASE)
    title_col = df.get("title",       pd.Series("", index=df.index)).fillna("")
    desc_col  = df.get("description", pd.Series("", index=df.index)).fillna("")
    def reject(title, desc):
        if JUNIOR_PAT.search(str(title)) or RESEARCH_ROLE_PAT.search(str(title)):
            return False
        return _has_desc(desc) and bool(pat.search(str(desc).lower()))
    mask = ~pd.Series([reject(t, d) for t, d in zip(title_col, desc_col)], index=df.index)
    logger.info(f"  Experience filter:  {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Experience filter")
    return df[mask].copy()


def filter_language(df: pd.DataFrame) -> pd.DataFrame:
    title_col = df.get("title", pd.Series("", index=df.index)).fillna("")
    desc_col  = _lower(df.get("description", pd.Series(index=df.index, dtype=str)))
    def reject(title, desc):
        return _has_desc(desc) and should_reject_language(desc, is_research=bool(RESEARCH_ROLE_PAT.search(str(title))))
    mask = ~pd.Series([reject(t, d) for t, d in zip(title_col, desc_col)], index=df.index)
    logger.info(f"  Language filter:    {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Language filter")
    return df[mask].copy()


def filter_noise(df: pd.DataFrame) -> pd.DataFrame:
    title_col = df.get("title", pd.Series("", index=df.index)).fillna("")
    def _reject(title: str) -> bool:
        t = str(title)
        if NOISE_TITLE_PAT.search(t):
            return True
        if not RESEARCH_ROLE_PAT.search(t) and NON_FULLTIME_TITLE_PAT.search(t):
            return True
        return False
    mask = ~title_col.apply(_reject)
    logger.info(f"  Noise filter:       {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Noise filter")
    return df[mask].copy()


FREELANCE_CONTRACT_PAT = re.compile(
    r"(\b€?\d{3,4}\s*(€|eur|euro)?\s*(per|/|pro)\s*(day|tag)\b|\btagessatz\b|\bfreelance\s+contract\b|\bfreelancer\s+contract\b)",
    re.IGNORECASE,
)

ZEITARBEIT_PAT = _kw_pat(REJECT_EMPLOYMENT_TYPES) if REJECT_EMPLOYMENT_TYPES else re.compile(
    r"\b(arbeitnehmer\u00fcberlassung|zeitarbeit|leiharbeit|personal\u00fcberlassung)\b", re.IGNORECASE
)

AGGREGATOR_COMPANY_PAT = _kw_pat(AGGREGATOR_COMPANIES) if AGGREGATOR_COMPANIES else re.compile(
    r"\b(fetchjobs\.co|jobleads|jooble|adzuna)\b", re.IGNORECASE
)


def filter_job_type(df: pd.DataFrame) -> pd.DataFrame:
    title_col    = df.get("title",       pd.Series("", index=df.index)).fillna("")
    company_col  = df.get("company",     pd.Series("", index=df.index)).fillna("")
    job_type_col = _lower(df.get("job_type", pd.Series("", index=df.index)))
    desc_col     = df.get("description", pd.Series("", index=df.index)).fillna("")
    def keep(title, company, jtype, desc) -> bool:
        t_str = str(title)
        c_str = str(company)
        d_str = str(desc)
        if jtype.strip() in REJECT_JOB_TYPES:
            return False
        if not RESEARCH_ROLE_PAT.search(t_str) and NON_FULLTIME_TITLE_PAT.search(t_str):
            return False
        if FREELANCE_CONTRACT_PAT.search(d_str) or FREELANCE_CONTRACT_PAT.search(t_str):
            return False
        if ZEITARBEIT_PAT.search(d_str) or ZEITARBEIT_PAT.search(t_str):
            return False
        if AGGREGATOR_COMPANY_PAT.search(c_str):
            return False
        return True
    mask = pd.Series([keep(t, c, jt, d) for t, c, jt, d in zip(title_col, company_col, job_type_col, desc_col)], index=df.index)
    logger.info(f"  Job-type filter:    {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Job-type filter")
    return df[mask].copy()



def filter_applicants(df: pd.DataFrame) -> pd.DataFrame:
    from src.core.utils import _parse_applicant_count
    app_col = None
    for candidate in ("applicant_count", "num_applicants", "applicants"):
        if candidate in df.columns:
            app_col = candidate
            break
            
    if app_col is None:
        logger.info(f"  Applicant filter (<= {MAX_APPLICANTS}): {len(df):4d} / {len(df)} kept  (no applicant column — skipped)")
        return df.copy()

    def keep(val) -> bool:
        count = _parse_applicant_count(val)
        return count is None or count <= MAX_APPLICANTS

    mask = df[app_col].apply(keep)
    removed = int((~mask).sum())
    logger.info(f"  Applicant filter (<= {MAX_APPLICANTS}): {mask.sum():4d} / {len(df)} kept  ({removed} removed with > {MAX_APPLICANTS} applicants)")
    _log_removed(df, mask, "Applicant filter")
    return df[mask].reset_index(drop=True)


NON_CS_RESEARCH_PAT = _kw_pat(NON_CS_RESEARCH_KEYWORDS) if NON_CS_RESEARCH_KEYWORDS else re.compile(r"(?!x)x")

WINDOWS_SYSADMIN_PAT = re.compile(
    r"\b(windows\s+server|powershell|active\s+directory|mcsa|mcse)\b",
    re.IGNORECASE,
)

def filter_research_cs(df: pd.DataFrame) -> pd.DataFrame:
    title_col = df.get("title",       pd.Series("", index=df.index)).fillna("")
    desc_col  = df.get("description", pd.Series("", index=df.index)).fillna("")
    def keep(title, desc) -> bool:
        t_str = str(title)
        d_str = str(desc)
        if not RESEARCH_ROLE_PAT.search(t_str):
            return True
        if NON_CS_RESEARCH_PAT.search(t_str) or NON_CS_RESEARCH_PAT.search(d_str):
            return False
        if not _has_desc(d_str):
            return True
        return bool(CS_KEYWORD_PAT.search(d_str))
    mask = pd.Series([keep(t, d) for t, d in zip(title_col, desc_col)], index=df.index)
    logger.info(f"  Research CS filter: {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Research CS filter")
    return df[mask].copy()


CORE_TARGET_TITLE_PAT = _kw_pat(CORE_TARGET_KEYWORDS)

ADMIN_INFRA_PAT = re.compile(
    r"\b(intune|entra\s+id|sccm|active\s+directory)\b",
    re.IGNORECASE,
)

VERIFIED_STACK_PAT = _kw_pat(CS_RELEVANCE_KEYWORDS)
OPTIONAL_PHRASE_PAT = re.compile(
    r"\b(wie|oder|bevorzugt|optional|beispielsweise|bspw\.|alternativ|oder\s+vergleichbar)\b",
    re.IGNORECASE,
)


def filter_forbidden_tech(df: pd.DataFrame) -> pd.DataFrame:
    title_col = df.get("title", pd.Series("", index=df.index)).fillna("")
    desc_col  = df.get("description", pd.Series("", index=df.index)).fillna("")
    def _reject(title: str, desc: str) -> bool:
        t = str(title)
        d = str(desc)
        text = t + " " + d

        # Priority 1: Protected Core Target & CS Titles
        if CORE_TARGET_TITLE_PAT.search(t) or CS_CORE_TITLE_PAT.search(t):
            if HARD_FORBIDDEN_TECH_PAT.search(t):
                return True
            return False

        # Priority 2: Non-core titles
        if HARD_FORBIDDEN_TECH_PAT.search(text):
            return True

        if WINDOWS_SYSADMIN_PAT.search(t) or (WINDOWS_SYSADMIN_PAT.search(d) and not re.search(r'\b(linux|docker|kubernetes|python|c\+\+|terraform|cloud|azure|aws|gcp)\b', text, re.IGNORECASE)):
            return True

        if ADMIN_INFRA_PAT.search(text):
            return True
        return bool(FORBIDDEN_TECH_PAT.search(t))
    mask = ~pd.Series([_reject(t, d) for t, d in zip(title_col, desc_col)], index=df.index)
    logger.info(f"  Forbidden tech filter: {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Forbidden tech filter")
    return df[mask].copy()


def filter_cs_relevance(df: pd.DataFrame) -> pd.DataFrame:
    title_col = df.get("title", pd.Series("", index=df.index)).fillna("")
    def _reject(title: str) -> bool:
        t = str(title)
        if RESEARCH_ROLE_PAT.search(t):
            return False
        return not bool(CS_CORE_TITLE_PAT.search(t))
    mask = ~title_col.apply(_reject)
    logger.info(f"  CS relevance filter:  {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "CS relevance filter")
    return df[mask].copy()


def compute_job_score(row) -> tuple[int, str]:
    """Compute candidate match score (0 to 100) and extracted matched skills string."""
    from src.config import VERIFIED_SKILLS
    title = str(row.get('title', '') or '').strip()
    company = str(row.get('company', '') or '').strip()
    desc = str(row.get('description', '') or '').strip()
    title_lower = title.lower()
    company_lower = company.lower()
    desc_lower = desc.lower()
    text = f"{title_lower} {company_lower} {desc_lower}"
    
    matched = []
    skill_pts = 0
    
    for skill in VERIFIED_SKILLS:
        skill_lower = skill.lower()
        if skill_lower in text:
            display = skill.upper() if len(skill) <= 4 or skill.lower() in ('python', 'linux', 'docker', 'kafka', 'flink', 'aws', 'bash', 'sql', 'qt') else skill.title()
            if display not in matched:
                matched.append(display)
            skill_pts += 6

    target_role_terms = ['software engineer', 'backend', 'linux', 'devops', 'data engineer', 'c++', 'python', 'cloud', 'system', 'embedded', 'security']
    for term in target_role_terms:
        if term in title_lower:
            skill_pts += 5

    date_str = str(row.get('date_posted', '') or row.get('first_seen', '') or '').strip()
    date_pts = 25
    if date_str and date_str.lower() not in ("nan", "none", "nat", "", "invalid"):
        try:
            dt = pd.to_datetime(date_str, utc=True, errors="coerce")
            if not pd.isna(dt):
                now = datetime.now(tz=timezone.utc)
                age_hours = (now - dt).total_seconds() / 3600.0
                if age_hours < 24:
                    date_pts = max(10, min(50, int(50 - age_hours)))
                elif age_hours < 72:
                    date_pts = 35
                elif age_hours < 168:
                    date_pts = 25
                else:
                    date_pts = 15
        except Exception:
            date_pts = 25

    raw_score = skill_pts + date_pts
    penalty = 0

    if re.search(r'\b(senior|sr\.?|lead|principal|head\s+of|director|architect|architekt)\b', title_lower):
        if not re.search(r'\b(junior|jr\.?|werkstudent|intern|trainee)\b', title_lower):
            penalty += 30

    clean_desc_for_exp = re.sub(
        r'(seit|über|tradition\s+von|history\s+of|provider\s+with|experience\s+of|besteht\s+seit)\s*\d+\s*(jahren?|years?)',
        '', desc_lower
    )
    
    high_exp_match = re.search(
        r'(\b[5-9]\+\s*years?|\b10\+\s*years?|\bmindestens\s+[5-9]\s+jahre|\bminimum\s+[5-9]\s+years|\b[5-9]\s+years\s+of\s+experience|\b[5-9]\s+jahre\s+berufserfahrung)',
        clean_desc_for_exp
    )
    if high_exp_match and not re.search(r'\b(0[–-]5|1[–-]5|0-5|1-5)\b', clean_desc_for_exp):
        penalty += 25

    total_score = max(0, min(100, raw_score - penalty))
    matched_str = ", ".join(matched[:6])
    return total_score, matched_str


def filter_by_score(df: pd.DataFrame, min_score: int = 20) -> pd.DataFrame:
    if df.empty:
        return df
    scores = []
    matched_skills_list = []
    for _, row in df.iterrows():
        score, skills = compute_job_score(row)
        scores.append(score)
        matched_skills_list.append(skills)
    df = df.copy()
    df["score"] = scores
    if "matched_skills" not in df.columns or df["matched_skills"].isna().all():
        df["matched_skills"] = matched_skills_list
    mask = df["score"] >= min_score
    logger.info(f"  Score filter (score >= {min_score}): {mask.sum():4d} / {len(df)} kept  ({(~mask).sum()} removed)")
    _log_removed(df, mask, "Score filter")
    return df[mask].copy()


def filter_empty_description(df: pd.DataFrame, min_chars: int = 150) -> pd.DataFrame:
    """Drop jobs where the description is empty or too short to be evaluated.
    
    Empty descriptions cannot pass language gate, seniority, or tech checks.
    They only waste Gemini API calls and produce phantom APPROVED entries (score=0).
    
    min_chars=150: enough to detect 'Link: https://...' only postings (< 50 chars)
    while keeping sparse-but-valid German postings.
    """
    before = len(df)
    if before == 0:
        return df
    desc_col = df.get("description", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    mask = desc_col.str.len() >= min_chars
    removed = before - mask.sum()
    if removed > 0:
        logger.info(f"  Empty description filter: {mask.sum():4d} / {before} kept  ({removed} link-only/empty jobs removed)")
        _log_removed(df, mask, "Empty description filter")
    return df[mask].copy()


def apply_filters(df: pd.DataFrame, max_days: int | None = None, is_linkedin: bool = False) -> pd.DataFrame:
    if df.empty:
        return df
    if is_linkedin:
        df = filter_reposted(df)
    df = filter_date(df, max_days=max_days, is_linkedin=is_linkedin)
    df = filter_empty_description(df)   # ← Drop link-only / empty-desc jobs before any evaluation
    df = filter_seniority(df)
    df = filter_experience(df)
    df = filter_noise(df)
    df = filter_cs_relevance(df)
    df = filter_research_cs(df)
    df = filter_forbidden_tech(df)
    df = filter_language(df)
    if is_linkedin:
        df = filter_job_type(df)
        df = filter_applicants(df)
    df = filter_by_score(df, min_score=20)
    return df


CATALOG_DEDUP_FILES = [
    "data/all_combined.csv",
    "data/all_combined_backup.csv",
    "data/ai_approved.csv",
    "data/ba_all_time.csv",
    "data/linkedin_all_time.csv",
    "data/indeed_all_time.csv",
    
]


def filter_against_existing_catalog(
    df: pd.DataFrame,
    catalog_files: list[str] | None = None,
    db_path: str = "data/karriere.db",
) -> pd.DataFrame:
    """
    Comprehensively filters out any job that already exists in:
    1. Primary: The SQLite database (data/karriere.db) 'jobs' table.
    2. Fallback / legacy: Historical all-time CSV files.

    Checks by:
    1. Normalized job_url
    2. Normalized (title + company) composite key
    3. Description fingerprint hash
    """
    from src.core.utils import _normalize_company, _norm, _plain_url

    before = len(df)
    if before == 0:
        return df

    seen_urls: set[str] = set()
    seen_title_company: set[str] = set()
    seen_fingerprints: set[str] = set()

    # 1. Primary Source of Truth: SQLite Database (data/karriere.db)
    if db_path and os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT url, company, title, description FROM jobs")
            for u, c, t, d in cursor.fetchall():
                if u:
                    clean_u = _plain_url(str(u)).strip()
                    if clean_u:
                        seen_urls.add(clean_u)
                norm_t = _norm(str(t or ""))
                norm_c = _normalize_company(str(c or ""))
                if norm_t and norm_c:
                    seen_title_company.add(f"{norm_t}|||{norm_c}")
                if d:
                    fp = _desc_fingerprint(str(d).strip())
                    if fp and len(fp) > 50:
                        seen_fingerprints.add(fp)
            conn.close()
        except Exception as exc:
            logger.warning(f"Could not load existing jobs from SQLite {db_path}: {exc}")

    # 2. Legacy / fallback CSV catalog files
    if catalog_files is None:
        catalog_files = CATALOG_DEDUP_FILES

    for file_path in catalog_files:
        if not os.path.exists(file_path):
            continue
        try:
            cat_df = pd.read_csv(
                file_path,
                usecols=lambda c: c in ("job_url", "title", "company", "description"),
            )
        except Exception:
            continue

        if cat_df.empty:
            continue

        # 1. Collect URLs
        if "job_url" in cat_df.columns:
            for u in cat_df["job_url"].dropna().apply(_plain_url).str.strip():
                if u:
                    seen_urls.add(u)

        # 2. Collect Title + Company keys
        if "title" in cat_df.columns and "company" in cat_df.columns:
            for _, r in cat_df.iterrows():
                t = _norm(str(r.get("title", "")))
                c = _normalize_company(str(r.get("company", "")))
                if t and c:
                    seen_title_company.add(f"{t}|||{c}")

        # 3. Collect description fingerprints
        if "description" in cat_df.columns:
            for d in cat_df["description"].dropna().astype(str):
                d_str = d.strip()
                if d_str:
                    fp = _desc_fingerprint(d_str)
                    if fp and len(fp) > 50:
                        seen_fingerprints.add(fp)

    df = df.copy()

    def is_duplicate(row):
        # Check URL
        url = _plain_url(str(row.get("job_url", ""))).strip()
        if url and url in seen_urls:
            return True

        # Check Title + Company
        t = _norm(str(row.get("title", "")))
        c = _normalize_company(str(row.get("company", "")))
        if t and c and f"{t}|||{c}" in seen_title_company:
            return True

        # Check Description Fingerprint
        desc = str(row.get("description", "") or "").strip()
        if desc:
            fp = _desc_fingerprint(desc)
            if fp and len(fp) > 50 and fp in seen_fingerprints:
                return True

        return False

    mask = ~df.apply(is_duplicate, axis=1)
    df = df[mask].reset_index(drop=True)
    removed = before - len(df)
    logger.info(f"  Existing Catalog Dedup: {len(df):4d} / {before} kept ({removed} existing jobs eliminated from all_combined/all_strong)")
    return df
