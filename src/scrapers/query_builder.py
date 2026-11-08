"""Dynamic Scraper Query Builder.

Translates candidate profile target titles and archetype defaults into
portal-specific search queries (LinkedIn booleans, Bund RSS terms, XING keywords).
"""

from typing import Any, Optional
from src.core.archetypes import DomainArchetype, get_archetype


def build_portal_queries(profile: Optional[dict[str, Any]], portal: str) -> list[str]:
    """Generate search query strings tailored to candidate profile and portal syntax."""
    from src.config import BOOLEAN_QUERIES, BA_BROAD_QUERIES
    from src.scrapers.bund import BUND_QUERIES
    from src.scrapers.xing import XING_QUERIES

    portal_lower = portal.lower().strip()

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

    # Resolve target titles
    prof_titles = profile.get("target_titles") or []
    if not prof_titles and "job_search_preferences" in profile:
        prof_titles = profile["job_search_preferences"].get("titles") or []

    titles = list(dict.fromkeys(prof_titles + archetype.target_titles))
    if not titles:
        titles = list(archetype.target_titles)

    if portal_lower in ("linkedin", "indeed"):
        # Format as boolean search terms
        if archetype.domain_queries:
            # Inject explicit target titles if present
            if prof_titles:
                clean_titles = [f'"{t}"' if " " in t else t for t in prof_titles]
                title_bool = " OR ".join(clean_titles)
                return [title_bool] + archetype.domain_queries
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
        # Portals that take discrete terms
        return titles[:8]

    # Default portal queries
    return titles[:5]
