"""Dynamic Scraper Query Builder.

Translates candidate profile target titles and archetype defaults into
portal-specific search queries (LinkedIn booleans, Bund RSS terms, XING keywords).
"""

from typing import Any, Optional
from src.core.archetypes import DomainArchetype, get_archetype
from src.scrapers.routing import (
    get_eligible_portals_for_countries,
    get_portal_geo_params,
    normalize_portal_slug,
)

# Deterministic German/bilingual query equivalents keyed strictly on explicit
# software/data/cloud/security title stems so German portals (BA, Bund.de, XING)
# find German postings while non-CS profiles remain completely untouched.
_GERMAN_PORTAL_SYNONYMS: dict[str, list[str]] = {
    "python developer": ["Python Entwickler", "Softwareentwickler Python", "Python"],
    "backend developer": ["Backend Entwickler", "Softwareentwickler Backend"],
    "backend engineer": ["Backend Entwickler", "Softwareentwickler Backend"],
    "software engineer": ["Softwareentwickler", "Systementwickler"],
    "software developer": ["Softwareentwickler"],
    "data engineer": ["Data Engineer", "Datenbankentwickler"],
    "junior data engineer": ["Junior Data Engineer", "Data Engineer"],
    "c++ developer": ["C++ Entwickler", "Softwareentwickler C++"],
    "c++ software engineer": ["C++ Entwickler", "Systementwickler C++"],
    "embedded software engineer": ["Embedded Softwareentwickler", "Embedded Entwickler"],
    "devops engineer": ["DevOps Engineer", "Cloud Engineer"],
    "devsecops engineer": ["DevSecOps", "IT Security Engineer"],
    "cloud engineer": ["Cloud Engineer", "AWS Engineer"],
    "security analyst": ["IT Security Analyst", "IT-Sicherheit"],
    "it security engineer": ["IT Security Engineer", "IT-Sicherheit"],
    "research software engineer": ["Wissenschaftlicher Mitarbeiter Informatik", "Research Software Engineer"],
    "ai engineer": ["AI Engineer", "Data AI Engineer"],
    "applied ai engineer": ["Data AI Engineer", "AI Engineer"],
    "software integration engineer": ["Software Integration Engineer", "Systementwickler"],
    "test automation engineer": ["Test Automation Engineer", "Software Test Engineer"],
}

_CS_DISCIPLINE_MARKERS = (
    "software", "data", "system", "computer", "cs", "cloud", "devops",
    "devsecops", "security", "backend", "python", "embedded", "ai", "ml",
    "platform", "informatik",
)


def get_candidate_eligible_portals(profile: Optional[dict[str, Any]]) -> list[str]:
    """Determine which portals can be queried based on candidate's target countries."""
    if not profile:
        return get_eligible_portals_for_countries(["Germany"])
    prefs = profile.get("job_search_preferences") or {}
    countries = prefs.get("countries") or []
    return get_eligible_portals_for_countries(countries)


def build_portal_search_queries(portal: str, profile: Optional[dict[str, Any]]) -> list[str]:
    """Generate search queries for a portal given candidate profile (portal, profile signature)."""
    return build_portal_queries(profile, portal)


def build_portal_queries(profile: Optional[dict[str, Any]], portal: str) -> list[str]:
    """Generate search query strings tailored to candidate profile and portal syntax."""
    from src.config import BOOLEAN_QUERIES, BA_BROAD_QUERIES
    from src.scrapers.bund import BUND_QUERIES
    from src.scrapers.xing import XING_QUERIES

    portal_lower = normalize_portal_slug(portal)

    if not profile:
        if portal_lower in ("linkedin", "indeed"):
            return list(BOOLEAN_QUERIES) if BOOLEAN_QUERIES else ["Software Engineer"]
        elif portal_lower == "bund":
            return list(BUND_QUERIES)
        elif portal_lower == "xing":
            return list(XING_QUERIES)
        elif portal_lower == "ba":
            return list(BA_BROAD_QUERIES) if BA_BROAD_QUERIES else ["Softwareentwickler"]
        return ["Software Engineer"]

    arch_slug = profile.get("archetype")
    archetype: DomainArchetype = get_archetype(arch_slug)

    # Resolve target titles: prioritize user's custom filter_rules
    filter_rules = profile.get("filter_rules") or {}
    prof_titles = filter_rules.get("target_titles")
    if not prof_titles:
        prof_titles = profile.get("target_titles") or []
    if not prof_titles and "job_search_preferences" in profile:
        prof_titles = profile["job_search_preferences"].get("titles") or []

    # If user provided explicit titles (or filter_rules), use them directly without polluting with static archetypes
    if prof_titles:
        titles = list(dict.fromkeys(prof_titles))
    else:
        titles = list(archetype.target_titles)

    if portal_lower in ("linkedin", "indeed"):
        # Format as boolean search terms
        if prof_titles:
            clean_titles = [f'"{t}"' if " " in t else t for t in prof_titles]
            # Group into chunks of 3-4 titles
            queries = []
            chunk_size = 3
            for i in range(0, len(clean_titles), chunk_size):
                chunk = clean_titles[i : i + chunk_size]
                queries.append(" OR ".join(chunk))
            return queries

        if archetype.domain_queries:
            return list(archetype.domain_queries)

        # Fallback to grouped booleans of titles
        queries = []
        chunk_size = 3
        for i in range(0, len(titles), chunk_size):
            chunk = titles[i : i + chunk_size]
            formatted = " OR ".join(f'"{t}"' if " " in t else t for t in chunk)
            queries.append(formatted)
        return queries or list(BOOLEAN_QUERIES)

    elif portal_lower in ("bund", "xing", "ba"):
        # Start from the candidate's own titles, prioritize explicit ba_queries when
        # present on a CS profile, then enrich IT/CS titles with deterministic German
        # equivalents so DACH portals don't starve on English-only titles.
        expanded = list(titles)

        if portal_lower == "ba":
            prefs = profile.get("job_search_preferences") or {}
            custom_ba = prefs.get("ba_queries") or []
            disc = str(filter_rules.get("discipline") or "").lower().strip()
            cs_arch = (arch_slug or "") in (
                "", "toyanath", "systems_engineering", "data_engineering",
                "backend_platform", "devsecops", "cpp_integration",
            )
            disc_ok = (not disc and cs_arch) or any(m in disc for m in _CS_DISCIPLINE_MARKERS)
            if custom_ba and disc_ok:
                for q_term in custom_ba:
                    if q_term and q_term not in expanded:
                        expanded.append(q_term)

        for t in titles:
            for syn in _GERMAN_PORTAL_SYNONYMS.get(str(t).strip().lower(), []):
                if syn not in expanded:
                    expanded.append(syn)

        limit = 22 if portal_lower == "ba" else 14
        return list(dict.fromkeys(expanded))[:limit]

    # Default portal queries
    return titles[:5]
