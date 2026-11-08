"""Dynamic, multi-tenant job filtering engine.

Compiles candidate-specific regex filters based on user archetype and profile,
preventing hardcoded CS / data engineering filters from contaminating candidates
in other disciplines (e.g. Civil, Mechanical, DevSecOps).
"""

import re
from typing import Any, Optional

from src.core.archetypes import DomainArchetype, get_archetype


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
    ):
        self.user_id = user_id
        self.archetype = archetype
        self.target_titles = target_titles
        self.relevance_keywords = relevance_keywords
        self.noise_keywords = noise_keywords
        self.seniority_keywords = seniority_keywords or UNIVERSAL_SENIORITY_KEYWORDS
        self.german_level = german_level

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

        # 1. Target titles: Explicit profile titles merged with archetype defaults
        prof_titles = profile.get("target_titles") or []
        if not prof_titles and "job_search_preferences" in profile:
            prof_titles = profile["job_search_preferences"].get("titles") or []

        target_titles = list(dict.fromkeys(prof_titles + archetype.target_titles))

        # 2. Relevance keywords: Candidate skills merged with archetype relevance
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

        # 3. Noise keywords: Universal spam + archetype forbidden noise
        noise_keywords = list(dict.fromkeys(UNIVERSAL_SPAM_KEYWORDS + archetype.forbidden_noise))

        # User negative keywords if any
        pref_neg = profile.get("job_search_preferences", {}).get("negative_keywords") or []
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

    # 3. Target Title Match (Primary gate)
    title_match = ctx.target_title_pat.search(title)

    # 4. Relevance Match in Description
    relevance_match = ctx.relevance_pat.search(full_text)

    if not title_match and not relevance_match:
        return False, "rejected: missing target_title and domain relevance"

    return True, ""
