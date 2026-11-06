import json
import pytest
from unittest.mock import patch, MagicMock

from src.scrapers.ashby import (
    parse_ashby_job,
    fetch_ashby_company,
    load_ashby_company_pool,
)


SAMPLE_ASHBY_JOB = {
    "id": "abc-123-def",
    "title": "Senior Python Backend Engineer",
    "department": "Engineering",
    "team": "Core Platform",
    "employmentType": "FullTime",
    "location": "Berlin, Germany",
    "secondaryLocations": [],
    "publishedAt": "2026-11-06T12:00:00.000Z",
    "isListed": True,
    "isRemote": True,
    "workplaceType": "Hybrid",
    "address": {
        "postalAddress": {
            "addressCountry": "Germany",
            "addressLocality": "Berlin"
        }
    },
    "jobUrl": "https://jobs.ashbyhq.com/langdock/abc-123-def",
    "applyUrl": "https://jobs.ashbyhq.com/langdock/abc-123-def/application",
    "descriptionPlain": "We are seeking a Senior Python Backend Engineer with PyFlink, FastAPI, and Kafka experience.",
    "descriptionHtml": "<p>We are seeking a Senior Python Backend Engineer with PyFlink, FastAPI, and Kafka experience.</p>"
}

SAMPLE_US_ONLY_JOB = {
    "id": "us-only-999",
    "title": "Account Executive",
    "department": "Sales",
    "employmentType": "FullTime",
    "location": "San Francisco, CA, USA",
    "isRemote": False,
    "jobUrl": "https://jobs.ashbyhq.com/langdock/us-only-999",
    "descriptionPlain": "US sales role."
}


def test_parse_ashby_job():
    job = parse_ashby_job(SAMPLE_ASHBY_JOB, company_slug="langdock")
    assert job is not None
    assert job["title"] == "Senior Python Backend Engineer"
    assert job["company"] == "Langdock"
    assert job["location"] == "Berlin, Germany"
    assert "jobs.ashbyhq.com/langdock/abc-123-def" in job["job_url"]
    assert "FastAPI, and Kafka" in job["description"]
    assert job["date_posted"] == "2026-11-06"
    assert job["applicant_count"] == 0


def test_ashby_regional_filter():
    # German hybrid job should be kept
    job_de = parse_ashby_job(SAMPLE_ASHBY_JOB, company_slug="langdock")
    assert job_de is not None

    # US-only on-site job should be rejected
    job_us = parse_ashby_job(SAMPLE_US_ONLY_JOB, company_slug="langdock")
    assert job_us is None


@patch("src.scrapers.ashby.requests.get")
def test_fetch_ashby_company(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobs": [SAMPLE_ASHBY_JOB, SAMPLE_US_ONLY_JOB]
    }
    mock_get.return_value = mock_resp

    jobs = fetch_ashby_company("langdock")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Python Backend Engineer"
    assert jobs[0]["company"] == "Langdock"

