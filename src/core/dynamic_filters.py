"""Dynamic, multi-tenant job filtering engine.

Compiles candidate-specific regex filters based on user archetype and profile,
preventing hardcoded CS / data engineering filters from contaminating candidates
in other disciplines (e.g. Civil, Mechanical, DevSecOps).
"""

import re
from typing import Any, Optional, List, Dict
import pandas as pd

from src.core.archetypes import DomainArchetype, get_archetype
from src.scrapers.routing import is_dach_region, DACH_REGIONS
from src.core.filters import (
    AGGREGATOR_COMPANY_PAT,
    HIGH_EXP_PATTERNS,
    JUNIOR_PAT,
    NON_FULLTIME_TITLE_PAT,
    RESEARCH_ROLE_PAT,
    SENIOR_DESC_PAT,
    ZEITARBEIT_PAT,
    ZEITARBEIT_SUFFIX_PAT,
    filter_language,
    filter_location,
)

_HIGH_EXP_PAT = re.compile("|".join(HIGH_EXP_PATTERNS), re.IGNORECASE)


def extract_language_level(languages: Any, lang_name: str, default: str = "") -> str:
    """Extract language proficiency level from either dict or list-of-dicts format."""
    if not languages:
        return default
    if isinstance(languages, dict):
        val = languages.get(lang_name)
        if isinstance(val, dict):
            return str(val.get("level") or val.get("proficiency") or default)
        if isinstance(val, str) and val:
            return val
    elif isinstance(languages, list):
        for item in languages:
            if isinstance(item, dict):
                name = item.get("language") or item.get("name") or ""
                if str(name).strip().lower() == lang_name.strip().lower():
                    return str(item.get("level") or item.get("proficiency") or default)
            elif isinstance(item, str) and lang_name.lower() in item.lower():
                return item
    return default


UNIVERSAL_SPAM_KEYWORDS: list[str] = [
    "initiativbewerbung",
    "initiativ",
    "talents wanted",
    "talent pool",
    "spontanbewerbung",
    "quereinsteiger",
    "lagerhelfer",
    "call center",
    "kundenservice telefon",
    "reinigungskraft",
    "küchenhilfe",
    "servicekraft gastronomie",
    "zeitungszusteller",
    "kurierfahrer",
    "promoter",
    "telemarketing",
    "vertriebsassistent outbound",
]

UNIVERSAL_SENIORITY_KEYWORDS: list[str] = [
    "head of",
    "director",
    "vice president",
    "vp",
    "chief",
    "cio",
    "cto",
    "cfo",
    "ceo",
    "principal",
    "geschäftsführer",
    "geschäftsführerin",
    "bereichsleiter",
    "bereichsleiterin",
    "abteilungsleiter",
    "managing partner",
    "equity partner",
]

_JUNIOR_MID_SENIORITY_PAT = re.compile(
    r"\b(senior|sr\.?|lead|staff|distinguished|fellow|leiter(?:in)?|teamleit\w*|abteilungsleit\w*|bereichsleit\w*|architekt(?:in)?|architect|manager)\b",
    re.IGNORECASE,
)

_JUNIOR_MID_EXCEPTION_PAT = re.compile(
    r"\b(junior|jr\.?|mid|regular|associate|entry|berufseinsteiger|all\s+levels)\b",
    re.IGNORECASE,
)

_CS_FLEX_TITLES: list[str] = [
    "Software Engineer",
    "Software Developer",
    "Softwareentwickler",
    "Softwareentwicklung",
    "Anwendungsentwickler",
    "Backend Engineer",
    "Backend Developer",
    "Backend Entwickler",
    "Data Engineering",
    "Platform Engineer",
    "Cloud Engineer",
    "Security Engineer",
    "IT Security Engineer",
    "Integration Engineer",
    "Solution Engineer",
    "Software Test Engineer",
    "Test Automation Engineer",
    "Founding Engineer",
    "Forward Deployed Engineer",
    "Site Reliability Engineer",
    "Systems Engineer",
]

_CS_DISCIPLINE_MARKERS = (
    "software", "data", "system", "computer", "cs", "cloud", "devops",
    "devsecops", "security", "backend", "python", "embedded", "ai", "ml",
    "platform", "informatik", "stream",
)


def build_keyword_regex(*keyword_lists: list[str], word_boundary: bool = True) -> re.Pattern:
    """Build compiled regex OR-pattern respecting word boundaries for tech terms."""
    all_terms = [kw.strip() for lst in keyword_lists for kw in lst if kw and kw.strip()]
    if not all_terms:
        return re.compile(r"(?!x)x")

    parts = []
    for kw in all_terms:
        esc = re.escape(kw)
        if not word_boundary:
            parts.append(esc)
        elif not kw[0].isalnum() and kw[0] != "_":
            parts.append(rf"(?<![a-zA-Z0-9]){esc}(?![a-zA-Z0-9])")
        elif not kw[-1].isalnum() and kw[-1] != "_":
            parts.append(rf"\b{esc}(?![a-zA-Z0-9])")
        else:
            parts.append(rf"\b{esc}\b")

    pattern = "(?:" + "|".join(parts) + ")"
    return re.compile(pattern, re.IGNORECASE)


class UserFilterContext:
    """Compiled filtering patterns specific to an authenticated candidate profile."""

    def __init__(
        self,
        user_id: int,
        archetype: DomainArchetype,
        target_titles: list[str],
        relevance_keywords: list[str],
        noise_keywords: list[str],
        seniority_keywords: Optional[list[str]] = None,
        german_level: str = "B2",
        preferences: Optional[dict[str, Any]] = None,
        is_junior_mid: bool = False,
        reject_non_fulltime: bool = True,
        reject_staffing_agencies: bool = True,
        is_cs_profile: bool = False,
    ):
        self.user_id = user_id
        self.archetype = archetype
        self.target_titles = target_titles
        self.relevance_keywords = relevance_keywords
        self.noise_keywords = noise_keywords
        self.seniority_keywords = seniority_keywords or UNIVERSAL_SENIORITY_KEYWORDS
        self.german_level = german_level
        self.preferences = preferences or {}
        self.countries = self.preferences.get("countries") or ["Germany"]
        self.cities = self.preferences.get("cities") or []
        self.is_junior_mid = is_junior_mid
        self.reject_non_fulltime = reject_non_fulltime
        self.reject_staffing_agencies = reject_staffing_agencies
        self.is_cs_profile = is_cs_profile

        # Compiled Patterns
        self.target_title_pat = build_keyword_regex(self.target_titles)
        self.relevance_pat = build_keyword_regex(self.relevance_keywords)
        self.noise_pat = build_keyword_regex(self.noise_keywords)
        self.seniority_pat = build_keyword_regex(self.seniority_keywords)

    @classmethod
    def from_profile(cls, profile: dict[str, Any], user_id: Optional[int] = None) -> "UserFilterContext":
        """Instantiate UserFilterContext from a candidate profile record."""
        if not profile:
            arch = get_archetype("general_engineering")
            return cls(
                user_id=user_id or 0,
                archetype=arch,
                target_titles=arch.target_titles,
                relevance_keywords=arch.relevance_keywords,
                noise_keywords=UNIVERSAL_SPAM_KEYWORDS + arch.forbidden_noise,
            )

        if user_id is None:
            user_id = profile.get("user_id", profile.get("id", 0))
        arch_slug = profile.get("archetype")
        archetype = get_archetype(arch_slug)

        filter_rules = profile.get("filter_rules") or {}
        custom_titles = filter_rules.get("target_titles")
        custom_inclusions = filter_rules.get("inclusion_keywords")
        custom_exclusions = filter_rules.get("exclusion_keywords")

        discipline_low = str(filter_rules.get("discipline") or "").lower().strip()
        is_cs_profile = (
            archetype.slug in ("systems_engineering", "data_engineering", "backend_platform", "devsecops", "cpp_integration")
            or any(m in discipline_low for m in _CS_DISCIPLINE_MARKERS)
        )

        # 1. Target titles: Prioritize custom filter_rules
        if custom_titles:
            target_titles = list(dict.fromkeys(custom_titles))
        else:
            prof_titles = profile.get("target_titles") or []
            if not prof_titles and "job_search_preferences" in profile:
                prof_titles = profile["job_search_preferences"].get("titles") or []
            if prof_titles:
                target_titles = list(dict.fromkeys(prof_titles))
            else:
                target_titles = list(archetype.target_titles)

        # Enrich generalist systems profiles with full CS flex titles, while specialized CS
        # tenants only receive direct bilingual equivalents of their own target_titles.
        if archetype.slug in ("systems_engineering", "toyanath"):
            for extra_title in _CS_FLEX_TITLES:
                if extra_title not in target_titles:
                    target_titles.append(extra_title)
        elif is_cs_profile:
            from src.scrapers.query_builder import _GERMAN_PORTAL_SYNONYMS
            for t in list(target_titles):
                for syn in _GERMAN_PORTAL_SYNONYMS.get(str(t).strip().lower(), []):
                    if syn not in target_titles:
                        target_titles.append(syn)

        # 2. Relevance keywords: Always preserve candidate's own profile skills AND
        # merge with custom inclusion_keywords (plus archetype keywords when on-domain).
        extracted_skills: list[str] = []
        skills_raw = profile.get("skills")
        if isinstance(skills_raw, dict):
            for val in skills_raw.values():
                if isinstance(val, list):
                    extracted_skills.extend(str(v) for v in val if v)
                elif isinstance(val, str) and val:
                    extracted_skills.append(val)
        elif isinstance(skills_raw, list):
            extracted_skills.extend(str(v) for v in skills_raw if v)

        arch_kw = (
            []
            if (custom_inclusions and archetype.slug == "general_engineering")
            else archetype.relevance_keywords
        )
        relevance_keywords = list(
            dict.fromkeys((custom_inclusions or []) + extracted_skills + arch_kw)
        )

        # 3. Noise keywords: Universal spam + custom exclusions + archetype forbidden noise
        noise_keywords = list(dict.fromkeys(UNIVERSAL_SPAM_KEYWORDS + (custom_exclusions or []) + archetype.forbidden_noise))

        pref_dict = profile.get("job_search_preferences") or {}
        pref_neg = pref_dict.get("negative_keywords") or []
        noise_keywords.extend(pref_neg)

        sen_level = str(filter_rules.get("seniority_level") or "").lower()
        max_yrs = filter_rules.get("max_years_experience")
        try:
            max_yrs_num = float(max_yrs) if max_yrs is not None else None
        except (TypeError, ValueError):
            max_yrs_num = None
        is_junior_mid = (
            (max_yrs_num is not None and max_yrs_num <= 3)
            or (
                any(tok in sen_level for tok in ("junior", "entry", "mid", "associate"))
                and "senior" not in sen_level
            )
            or (max_yrs_num is None and not sen_level and archetype.slug == "systems_engineering")
        )
        if any(tok in t.lower() for t in target_titles for tok in ("senior", "principal", "lead", "staff", "manager")):
            is_junior_mid = False

        reject_non_fulltime = not any(
            tok in " ".join(target_titles).lower()
            for tok in ("werkstudent", "intern", "praktik", "working student", "teilzeit", "part-time", "trainee")
        )
        reject_staffing_agencies = not any(
            tok in " ".join(target_titles).lower()
            for tok in ("recruiter", "personalvermittl", "zeitarbeit", "staffing")
        )

        german_level = (
            profile.get("german_level")
            or extract_language_level(profile.get("languages"), "German", "B2")
            or "B2"
        )

        return cls(
            user_id=user_id,
            archetype=archetype,
            target_titles=target_titles,
            relevance_keywords=relevance_keywords,
            noise_keywords=noise_keywords,
            seniority_keywords=UNIVERSAL_SENIORITY_KEYWORDS,
            german_level=str(german_level),
            preferences=pref_dict,
            is_junior_mid=is_junior_mid,
            reject_non_fulltime=reject_non_fulltime,
            reject_staffing_agencies=reject_staffing_agencies,
            is_cs_profile=is_cs_profile,
        )


def filter_job_for_user(job: dict[str, Any], ctx: UserFilterContext) -> tuple[bool, str]:
    """Evaluate whether a job listing matches the candidate's dynamic filter context.

    Returns:
        (True, "") if approved.
        (False, reason_string) if rejected.
    """
    title = str(job.get("title") or "")
    company = str(job.get("company") or "")
    desc = str(job.get("description") or "")
    full_text = f"{title}\n{company}\n{desc}"

    # 1. Noise / Universal Spam
    noise_match = ctx.noise_pat.search(title) or ctx.noise_pat.search(company)
    if noise_match:
        return False, f"noise: matched '{noise_match.group(0)}'"

    # 1b. Aggregators / Staffing Agencies / Zeitarbeit
    if ctx.reject_staffing_agencies:
        if AGGREGATOR_COMPANY_PAT.search(company):
            return False, f"noise: staffing/aggregator company '{company}'"
        if ZEITARBEIT_PAT.search(full_text) or ZEITARBEIT_SUFFIX_PAT.search(title) or ZEITARBEIT_SUFFIX_PAT.search(desc):
            return False, "noise: temporary staffing / Zeitarbeit"

    # 1c. Non-Fulltime Roles (Werkstudent / Intern / Praktikum / Thesis / Ausbildung)
    if ctx.reject_non_fulltime:
        if not RESEARCH_ROLE_PAT.search(title) and NON_FULLTIME_TITLE_PAT.search(title):
            if not re.search(r"\b(vollzeit|full[- ]?time)\b", f"{title}\n{desc}", re.IGNORECASE):
                return False, f"employment_type: non-fulltime title '{title}'"

    # 2. Seniority Gate (executive/leadership titles apply across all non-executive profiles)
    seniority_match = ctx.seniority_pat.search(title)
    if seniority_match:
        return False, f"seniority: matched '{seniority_match.group(0)}' in title"

    # 3. Location Gate (check candidate's target countries/cities)
    job_loc = str(job.get("location") or "").strip()
    if job_loc:
        loc_df = pd.DataFrame([{"location": job_loc}])
        filtered_loc_df = filter_tenant_location(loc_df, ctx.preferences)
        if filtered_loc_df.empty:
            return False, f"location: '{job_loc}' outside target markets ({', '.join(ctx.countries)})"

    # 4. Regional Language Gate
    if desc:
        lang_df = pd.DataFrame([{"title": title, "description": desc}])
        filtered_lang_df = filter_tenant_language(lang_df, ctx.preferences, german_level=ctx.german_level)
        if filtered_lang_df.empty:
            return False, f"language: requires higher German proficiency than candidate profile ({ctx.german_level})"

    # 5. Target Title Match (Primary gate)
    title_match = ctx.target_title_pat.search(title)

    # 6. Relevance Match in Description
    relevance_match = ctx.relevance_pat.search(full_text)

    if not title_match and not relevance_match:
        return False, "rejected: missing target_title and domain relevance"

    # 7. Junior/Mid Seniority & Experience Ceiling (evaluated after domain relevance)
    if ctx.is_junior_mid:
        jm_match = _JUNIOR_MID_SENIORITY_PAT.search(title)
        if jm_match and not _JUNIOR_MID_EXCEPTION_PAT.search(title):
            return False, f"seniority: '{jm_match.group(0)}' exceeds candidate Junior/Mid target"
        if desc and not JUNIOR_PAT.search(title) and (SENIOR_DESC_PAT.search(desc) or _HIGH_EXP_PAT.search(desc)):
            return False, "seniority: description explicitly requires senior / 5+ years experience"

    return True, ""


def filter_tenant_location(df: pd.DataFrame, preferences: Dict[str, Any]) -> pd.DataFrame:
    """Filter jobs by location based on candidate tenant preferences.
    
    If candidate targets exclusively DACH, standard German location filter is applied.
    Otherwise, matches against candidate's allowed countries, cities, or remote listings.
    """
    if "location" not in df.columns or df.empty:
        return df.copy()

    countries = preferences.get("countries") or ["Germany"]
    cities = preferences.get("cities") or []

    # If exclusively targeting DACH, enforce the strict DACH/German location filter
    if is_dach_region(countries) and not any(c.strip().lower() not in DACH_REGIONS for c in countries):
        return filter_location(df)

    allowed_countries = [c.strip().lower() for c in countries if c and c.strip()]
    allowed_cities = [ci.strip().lower() for ci in cities if ci and ci.strip()]

    def _is_match(loc: Any) -> bool:
        if not loc or pd.isna(loc):
            return True  # Keep unspecified locations
        loc_l = str(loc).lower().strip()
        if not loc_l:
            return True
        if "remote" in loc_l:
            return True
        if any(c in loc_l for c in allowed_countries):
            return True
        if any(ci in loc_l for ci in allowed_cities):
            return True
        return False

    mask = df["location"].apply(_is_match)
    return df[mask].copy()


def filter_tenant_language(
    df: pd.DataFrame,
    preferences: Dict[str, Any],
    german_level: str = "B2",
) -> pd.DataFrame:
    """Apply language gates according to candidate's target regional markets and German proficiency.

    Non-DACH candidates (e.g. US, Canada, UK, Nepal) or candidates with C1/C2/Native German
    skip B2-level German rejection gates.
    """
    if df.empty:
        return df.copy()

    countries = preferences.get("countries") or ["Germany"]
    if not is_dach_region(countries):
        return df.copy()

    g_low = str(german_level or "B2").lower()
    if any(tok in g_low for tok in ("c1", "c2", "native", "muttersprach", "fließend", "fluent", "verhandlungssicher")):
        return df.copy()

    return filter_language(df)

