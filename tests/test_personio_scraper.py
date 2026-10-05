"""
tests/test_personio_scraper.py — Unit tests for the Personio XML feed scraper
"""

import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from src.scrapers.personio import (
    load_company_pool,
    fetch_company_xml,
    scrape_personio_network,
    SEED_FILE,
    _extract_ld_location,
    _is_allowed_region,
)


SAMPLE_PERSONIO_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position>
    <id>12345</id>
    <name>Python Software Engineer (m/w/d)</name>
    <office>Berlin</office>
    <department>Engineering</department>
    <employmentType>permanent</employmentType>
    <createdAt>2026-10-05T10:00:00+02:00</createdAt>
    <jobDescriptions>
      <jobDescription>
        <name>Your Role</name>
        <value><![CDATA[<p>Build <strong>scalable Python APIs</strong> and data pipelines.</p>]]></value>
      </jobDescription>
    </jobDescriptions>
  </position>
  <position>
    <id>67890</id>
    <name>Senior Lead Architect</name>
    <office>Munich</office>
    <department>Management</department>
    <employmentType>permanent</employmentType>
    <createdAt>2026-10-04T10:00:00+02:00</createdAt>
    <jobDescriptions>
      <jobDescription>
        <name>Overview</name>
        <value><![CDATA[Management role.]]></value>
      </jobDescription>
    </jobDescriptions>
  </position>
</workzag-jobs>
"""


def test_load_company_pool():
    """Verify company pool loads seed companies correctly."""
    pool = load_company_pool()
    assert isinstance(pool, list)
    assert len(pool) > 0
    assert "wattfox" in pool


def test_fetch_company_xml_parsing():
    """Verify parsing XML into clean structured job objects."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = SAMPLE_PERSONIO_XML
    mock_resp.text = SAMPLE_PERSONIO_XML.decode("utf-8")

    with patch("src.scrapers.personio.requests.get", return_value=mock_resp):
        jobs = fetch_company_xml("acme-corp")

    assert len(jobs) == 2
    j1 = jobs[0]
    assert j1["title"] == "Python Software Engineer (m/w/d)"
    assert j1["company"] == "Acme Corp"
    assert j1["location"] == "Berlin"
    assert "scalable Python APIs" in j1["description"]
    assert j1["job_url"] == "https://acme-corp.jobs.personio.de/job/12345"
    assert j1["job_type"] == "permanent"


@pytest.mark.parametrize(
    ("location", "allowed"),
    [
        ("Darmstadt, DE", True),
        ("Berlin, US", False),
        ("Remote, US", False),
        ("Buenos Aires, Argentina", False),
        ("Brussels, Belgium", True),
        ("Remote", True),
        ("Home office — London", False),
    ],
)
def test_location_gate_matches_complete_regions_and_delimited_country_codes(location, allowed):
    assert _is_allowed_region(location) is allowed


def test_json_ld_location_normalizes_iso_country_code():
    location = _extract_ld_location({
        "address": {"addressLocality": "Darmstadt", "addressCountry": "DE"}
    })

    assert location == "Darmstadt, Germany"


def test_xml_internship_type_is_normalized():
    xml = SAMPLE_PERSONIO_XML.replace(b"<employmentType>permanent</employmentType>", b"<employmentType>INTERN</employmentType>", 1)
    mock_resp = MagicMock(status_code=200, content=xml, text=xml.decode("utf-8"))

    with patch("src.scrapers.personio.requests.get", return_value=mock_resp):
        jobs = fetch_company_xml("acme-corp")

    assert jobs[0]["job_type"] == "internship"


def test_json_ld_internship_type_is_normalized():
    home = MagicMock(status_code=200, text='<a href="/job/42">')
    xml_missing = MagicMock(status_code=404, text="", content=b"")
    detail_html = """
    <script type="application/ld+json">
    {"@type":"JobPosting","title":"Research Intern","employmentType":"INTERN",
     "jobLocation":{"address":{"addressLocality":"Berlin","addressCountry":"DE"}}}
    </script>
    """
    detail = MagicMock(status_code=200, text=detail_html)

    with patch(
        "src.scrapers.personio.requests.get",
        side_effect=[xml_missing, xml_missing, home, detail],
    ):
        jobs = fetch_company_xml("acme-corp")

    assert jobs[0]["job_type"] == "internship"


def test_scrape_personio_network_flow():
    """Verify end-to-end scraper aggregation into DataFrame."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = SAMPLE_PERSONIO_XML
    mock_resp.text = SAMPLE_PERSONIO_XML.decode("utf-8")

    with patch("src.scrapers.personio.load_company_pool", return_value=["testcomp"]), \
         patch("src.scrapers.personio.requests.get", return_value=mock_resp):
        df = scrape_personio_network(max_workers=2)

    assert not df.empty
    assert len(df) == 2
    assert "title" in df.columns
    assert "job_url" in df.columns
    assert "description" in df.columns
