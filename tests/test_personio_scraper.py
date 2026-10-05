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
