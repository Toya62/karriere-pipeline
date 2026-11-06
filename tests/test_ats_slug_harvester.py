import json
import pytest
from unittest.mock import patch, MagicMock

from scripts.harvest_ats_slugs import (
    extract_ats_slug_from_url,
    append_slug_to_seed,
    probe_personio_slug,
    probe_ashby_slug,
)


def test_extract_ats_slug_from_url():
    # Personio
    assert extract_ats_slug_from_url("https://langdock.jobs.personio.de/job/12345") == ("personio", "langdock")
    assert extract_ats_slug_from_url("https://company-corp.jobs.personio.com/job/6789") == ("personio", "company-corp")
    assert extract_ats_slug_from_url("https://www.jobs.personio.de/job/123") is None  # 'www' rejected

    # Ashby
    assert extract_ats_slug_from_url("https://jobs.ashbyhq.com/qdrant/abc-def") == ("ashby", "qdrant")
    assert extract_ats_slug_from_url("https://jobs.ashbyhq.com/PostHog/123/application") == ("ashby", "posthog")

    # Greenhouse
    assert extract_ats_slug_from_url("https://boards.greenhouse.io/celonis/jobs/999") == ("greenhouse", "celonis")

    # Non-ATS
    assert extract_ats_slug_from_url("https://www.linkedin.com/jobs/view/123456") is None
    assert extract_ats_slug_from_url("https://www.xing.com/jobs/berlin-123") is None


def test_append_slug_to_seed(tmp_path, monkeypatch):
    test_seed = tmp_path / "seed_test.json"
    test_seed.write_text(json.dumps(["existing-co"]))

    monkeypatch.setattr("scripts.harvest_ats_slugs.PERSONIO_SEED_FILE", str(test_seed))

    # Existing slug -> False
    assert append_slug_to_seed("personio", "existing-co") is False

    # New valid slug -> True
    assert append_slug_to_seed("personio", "new-co") is True

    # Verify written file
    data = json.loads(test_seed.read_text())
    assert "new-co" in data
    assert "existing-co" in data


@patch("scripts.harvest_ats_slugs.requests.get")
def test_probe_personio_slug(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<workzag-jobs><position><id>1</id></position></workzag-jobs>"
    mock_get.return_value = mock_resp

    assert probe_personio_slug("testcompany") is True

    # Inactive XML feed
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    assert probe_personio_slug("nonexistent") is False


@patch("scripts.harvest_ats_slugs.requests.get")
def test_probe_ashby_slug(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jobs": [{"id": "1", "title": "Dev"}]}
    mock_get.return_value = mock_resp

    assert probe_ashby_slug("testashby") is True

    mock_resp.status_code = 404
    assert probe_ashby_slug("badashby") is False

