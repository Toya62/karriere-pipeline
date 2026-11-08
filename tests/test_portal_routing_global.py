"""Unit tests for regional portal routing and geo parameter resolution."""

from src.scrapers.routing import get_eligible_portals_for_countries, get_portal_geo_params


def test_dach_candidate_gets_all_portals():
    portals = get_eligible_portals_for_countries(["Germany"])
    assert "bund" in portals
    assert "ba" in portals
    assert "xing" in portals
    assert "linkedin" in portals
    assert "indeed" in portals
    assert "arbeitnow" in portals


def test_canadian_candidate_gets_global_portals_only():
    portals = get_eligible_portals_for_countries(["Canada"])
    assert "bund" not in portals
    assert "ba" not in portals
    assert "xing" not in portals
    assert "arbeitnow" not in portals
    assert "linkedin" in portals
    assert "indeed" in portals
    assert "greenhouse" in portals
    assert "ashby" in portals


def test_nepal_candidate_gets_global_portals_only():
    portals = get_eligible_portals_for_countries(["Nepal"])
    assert "bund" not in portals
    assert "ba" not in portals
    assert "xing" not in portals
    assert "linkedin" in portals


def test_indeed_and_linkedin_geo_params():
    params = get_portal_geo_params("indeed", {"countries": ["Canada"], "cities": ["Toronto"]})
    assert params["country"] == "ca"
    assert "Toronto" in params["location"]

    us_params = get_portal_geo_params("indeed", {"countries": ["United States"], "cities": ["New York"]})
    assert us_params["country"] == "us"
    assert "New York" in us_params["location"]

    li_params = get_portal_geo_params("linkedin", {"countries": ["United States"], "cities": ["New York"]})
    assert "New York" in li_params["location"]
    assert "United States" in li_params["location"]
