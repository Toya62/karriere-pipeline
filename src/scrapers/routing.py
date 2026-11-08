"""Regional portal routing and geo parameter resolution for multi-tenant SaaS scraping."""

from typing import Any, List, Dict

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


def get_portal_geo_params(portal: str, preferences: Dict[str, Any]) -> Dict[str, str]:
    """Resolve portal-specific search country code and location string."""
    countries = preferences.get("countries") or ["Germany"]
    cities = preferences.get("cities") or []

    country = countries[0] if countries else "Germany"
    city = cities[0] if cities else ""

    c_code = COUNTRY_CODE_MAP.get(country.strip().lower(), "de")
    if city and country:
        location = f"{city}, {country}"
    elif city:
        location = city
    else:
        location = country

    return {
        "country": c_code,
        "location": location,
        "city": city,
        "primary_country": country,
    }
