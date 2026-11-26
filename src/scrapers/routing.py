"""Regional portal routing and geo parameter resolution for multi-tenant SaaS scraping."""

import re
from typing import Any, List, Dict, Optional

DACH_REGIONS = {
    "germany", "deutschland", "de",
    "austria", "österreich", "at",
    "switzerland", "schweiz", "ch",
}

ALL_PORTALS = [
    "linkedin", "indeed", "ba", "bund", "xing", "personio", "ashby", "greenhouse", "arbeitnow"
]

GLOBAL_PORTALS = [
    "linkedin", "indeed", "greenhouse", "ashby"
]

COUNTRY_CODE_MAP = {
    "germany": "de",
    "deutschland": "de",
    "canada": "ca",
    "united states": "us",
    "usa": "us",
    "united kingdom": "gb",
    "uk": "gb",
    "nepal": "np",
    "india": "in",
    "switzerland": "ch",
    "austria": "at",
    "netherlands": "nl",
    "australia": "au",
}

COUNTRY_INDEED_MAP = {
    "de": "germany",
    "germany": "germany",
    "deutschland": "germany",
    "ca": "canada",
    "canada": "canada",
    "us": "usa",
    "usa": "usa",
    "united states": "usa",
    "uk": "uk",
    "gb": "uk",
    "united kingdom": "uk",
    "au": "australia",
    "australia": "australia",
    "ch": "switzerland",
    "switzerland": "switzerland",
    "at": "austria",
    "austria": "austria",
    "in": "india",
    "india": "india",
    "fr": "france",
    "france": "france",
    "nl": "netherlands",
    "netherlands": "netherlands",
}

CITY_COUNTRY_INFERENCE = {
    "toronto": "Canada",
    "vancouver": "Canada",
    "montreal": "Canada",
    "calgary": "Canada",
    "ottawa": "Canada",
    "scarborough": "Canada",
    "mississauga": "Canada",
    "edmonton": "Canada",
    "berlin": "Germany",
    "munich": "Germany",
    "münchen": "Germany",
    "hamburg": "Germany",
    "frankfurt": "Germany",
    "cologne": "Germany",
    "köln": "Germany",
    "stuttgart": "Germany",
    "düsseldorf": "Germany",
    "essen": "Germany",
    "london": "United Kingdom",
    "new york": "United States",
    "san francisco": "United States",
    "austin": "United States",
    "seattle": "United States",
    "chicago": "United States",
    "sydney": "Australia",
    "melbourne": "Australia",
    "zurich": "Switzerland",
    "zürich": "Switzerland",
    "vienna": "Austria",
    "wien": "Austria",
}


def is_dach_region(target_countries: List[str]) -> bool:
    """Check if any of the target countries falls within the DACH economic region."""
    if not target_countries:
        return True  # Default to DACH
    return any(c.strip().lower() in DACH_REGIONS for c in target_countries)


def get_eligible_portals_for_countries(target_countries: List[str]) -> List[str]:
    """Return list of scraping portals relevant for candidate's target markets."""
    if is_dach_region(target_countries):
        return list(ALL_PORTALS)
    return list(GLOBAL_PORTALS)


def get_portal_geo_params(
    portal: str,
    preferences: Dict[str, Any],
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Resolve portal-specific search country code and location string."""
    pref_dict = preferences or {}
    countries = [c for c in (pref_dict.get("countries") or []) if c and c.strip()]
    cities = [ci for ci in (pref_dict.get("cities") or []) if ci and ci.strip()]

    # Filter out placeholder 'Remote Worldwide' when resolving concrete physical country
    concrete_countries = [c for c in countries if c.lower() not in ("remote worldwide", "worldwide", "remote")]

    country = concrete_countries[0] if concrete_countries else ""
    city = cities[0] if cities else ""

    # Infer country from city or profile location if country wasn't explicitly given
    if not country:
        if city and city.lower() in CITY_COUNTRY_INFERENCE:
            country = CITY_COUNTRY_INFERENCE[city.lower()]
        elif profile:
            pers_loc = profile.get("personal_info", {}).get("location", "")
            for c_name in ("Canada", "United States", "United Kingdom", "Germany", "Australia", "India", "Nepal"):
                if c_name.lower() in pers_loc.lower():
                    country = c_name
                    break
            if not country:
                sugg = profile.get("recommended_filters", {}).get("suggested_countries") or []
                if sugg:
                    country = sugg[0]

    if not country:
        country = "Germany"

    c_code = COUNTRY_CODE_MAP.get(country.strip().lower(), "de")
    country_indeed = COUNTRY_INDEED_MAP.get(country.strip().lower(), COUNTRY_INDEED_MAP.get(c_code, "germany"))

    if city and country:
        location = f"{city}, {country}"
    elif city:
        location = city
    else:
        location = country

    return {
        "country": c_code,
        "country_indeed": country_indeed,
        "location": location,
        "city": city,
        "primary_country": country,
    }


def normalize_portal_slug(raw: Optional[str]) -> str:
    """Normalize a portal display label, alias, or URL to a canonical slug.

    Checks Bundesagentur markers ('arbeitsagentur', 'bundesagentur', 'agentur',
    word-boundary 'ba') BEFORE 'bund' so labels like 'Bundesagentur' or
    'Bundesagentur (BA)' never collide with 'bund'.
    """
    p = (raw or "").lower().strip()
    if not p:
        return ""
    if "indeed" in p:
        return "indeed"
    if "linkedin" in p or "licdn" in p:
        return "linkedin"
    if "xing" in p:
        return "xing"
    if (
        "arbeitsagentur" in p
        or "bundesagentur" in p
        or "agentur" in p
        or p == "ba"
        or bool(re.search(r"\bba\b", p))
    ):
        return "ba"
    if "bund" in p or "interamt" in p:
        return "bund"
    if "personio" in p:
        return "personio"
    if "ashby" in p:
        return "ashby"
    if "greenhouse" in p or "gh_jid" in p:
        return "greenhouse"
    if "arbeitnow" in p:
        return "arbeitnow"
    return p
