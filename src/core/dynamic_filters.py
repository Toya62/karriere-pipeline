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
from src.core.filters import filter_location, filter_language


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
    "partner",
]


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

        # Compiled Patterns
        self.target_title_pat = build_keyword_regex(self.target_titles)
        self.relevance_pat = build_keyword_regex(self.relevance_keywords)
        self.noise_pat = build_keyword_regex(self.noise_keywords)
        self.seniority_pat = build_keyword_regex(self.seniority_keywords)

    @classmethod
    def from_profile(cls, profile: dict[str, Any]) -> "UserFilterContext":
        """Instantiate UserFilterContext from a candidate profile record."""
        user_id = profile.get("user_id", profile.get("id", 0))
        arch_slug = profile.get("archetype")
        archetype = get_archetype(arch_slug)

        filter_rules = profile.get("filter_rules") or {}
        custom_titles = filter_rules.get("target_titles")
        custom_inclusions = filter_rules.get("inclusion_keywords")
        custom_exclusions = filter_rules.get("exclusion_keywords")

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

        # 2. Relevance keywords: Prioritize custom inclusion_keywords
        if custom_inclusions:
            relevance_keywords = list(dict.fromkeys(custom_inclusions))
        else:
            extracted_skills: list[str] = []
            skills_raw = profile.get("skills")
            if isinstance(skills_raw, dict):
                for val in skills_raw.values():
                    if isinstance(val, list):
                        extracted_skills.extend(val)
                    elif isinstance(val, str):
                        extracted_skills.append(val)
            elif isinstance(skills_raw, list):
                extracted_skills.extend(skills_raw)
            relevance_keywords = list(dict.fromkeys(extracted_skills + archetype.relevance_keywords))

        # 3. Noise keywords: Universal spam + custom exclusions + archetype forbidden noise
        noise_keywords = list(dict.fromkeys(UNIVERSAL_SPAM_KEYWORDS + (custom_exclusions or []) + archetype.forbidden_noise))

        pref_dict = profile.get("job_search_preferences") or {}
        pref_neg = pref_dict.get("negative_keywords") or []
        noise_keywords.extend(pref_neg)

        german_level = profile.get("german_level") or profile.get("languages", {}).get("German") or "B2"

        return cls(
            user_id=user_id,
            archetype=archetype,
            target_titles=target_titles,
            relevance_keywords=relevance_keywords,
            noise_keywords=noise_keywords,
            seniority_keywords=UNIVERSAL_SENIORITY_KEYWORDS,
            german_level=str(german_level),
            preferences=pref_dict,
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

    # 2. Seniority Gate (check in title)
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
        filtered_lang_df = filter_tenant_language(lang_df, ctx.preferences)
        if filtered_lang_df.empty:
            return False, "language: requires higher German proficiency than candidate profile"

    # 5. Target Title Match (Primary gate)
    title_match = ctx.target_title_pat.search(title)

    # 6. Relevance Match in Description
    relevance_match = ctx.relevance_pat.search(full_text)

    if not title_match and not relevance_match:
        return False, "rejected: missing target_title and domain relevance"

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


def filter_tenant_language(df: pd.DataFrame, preferences: Dict[str, Any]) -> pd.DataFrame:
    """Apply language gates according to candidate's target regional markets.

    Non-DACH candidates (e.g. US, Canada, UK, Nepal) skip German B2/C1 gates.
    DACH candidates enforce standard German level requirements.
    """
    if df.empty:
        return df.copy()

    countries = preferences.get("countries") or ["Germany"]
    if not is_dach_region(countries):
        return df.copy()

    return filter_language(df)

