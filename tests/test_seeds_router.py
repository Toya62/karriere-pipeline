import json
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app

client = TestClient(create_app())


def test_discover_direct_personio_seed(tmp_path, monkeypatch):
    test_seed = tmp_path / "seed_personio_companies.json"
    test_seed.write_text("[\"existing-comp\"]")
    test_db_slugs = tmp_path / "db_company_slugs.json"
    test_db_slugs.write_text("[\"existing-comp\"]")

    from scripts import harvest_ats_slugs
    monkeypatch.setattr(harvest_ats_slugs, "PERSONIO_SEED_FILE", str(test_seed))
    monkeypatch.setattr(harvest_ats_slugs, "DB_COMPANY_SLUGS_FILE", str(test_db_slugs))

    payload = {
        "url": "https://brand-new-comp.jobs.personio.de/job/12345",
        "company": "Brand New Comp GmbH",
        "source": "ats_page_visit",
    }
    resp = client.post("/api/seeds/discover", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["added"] is True
    assert data["ats_type"] == "personio"
    assert data["slug"] == "brand-new-comp"

    # Verify written to seed file
    with open(test_seed, "r") as f:
        seeds = json.load(f)
    assert "brand-new-comp" in seeds

    # Verify duplicate is rejected cleanly
    resp_dup = client.post("/api/seeds/discover", json=payload)
    assert resp_dup.status_code == 200
    assert resp_dup.json()["added"] is False
    assert resp_dup.json()["already_known"] is True


def test_discover_linkedin_redirect_param(tmp_path, monkeypatch):
    test_seed = tmp_path / "seed_personio_companies.json"
    test_seed.write_text("[]")
    test_db_slugs = tmp_path / "db_company_slugs.json"
    test_db_slugs.write_text("[]")

    from scripts import harvest_ats_slugs
    monkeypatch.setattr(harvest_ats_slugs, "PERSONIO_SEED_FILE", str(test_seed))
    monkeypatch.setattr(harvest_ats_slugs, "DB_COMPANY_SLUGS_FILE", str(test_db_slugs))

    raw_li = "https://www.linkedin.com/jobs/view/externalApply/4440931656?url=https%3A%2F%2Fdiscovered-via-linkedin.jobs.personio.de%2Fjob%2F999&urlHash=abc"
    resp = client.post("/api/seeds/discover", json={"url": raw_li, "source": "linkedin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["added"] is True
    assert data["ats_type"] == "personio"
    assert data["slug"] == "discovered-via-linkedin"


def test_discover_greenhouse_seed(tmp_path, monkeypatch):
    test_seed = tmp_path / "seed_greenhouse_companies.json"
    test_seed.write_text("[]")
    test_db_slugs = tmp_path / "db_company_slugs.json"
    test_db_slugs.write_text("[]")

    from scripts import harvest_ats_slugs
    monkeypatch.setattr(harvest_ats_slugs, "GREENHOUSE_SEED_FILE", str(test_seed))
    monkeypatch.setattr(harvest_ats_slugs, "DB_COMPANY_SLUGS_FILE", str(test_db_slugs))

    resp = client.post(
        "/api/seeds/discover",
        json={"url": "https://boards.greenhouse.io/targetscaleup/jobs/55", "source": "extension"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["added"] is True
    assert data["ats_type"] == "greenhouse"
    assert data["slug"] == "targetscaleup"


def test_list_seed_summary():
    resp = client.get("/api/seeds")
    assert resp.status_code == 200
    data = resp.json()
    assert "personio_seeds" in data
    assert "greenhouse_seeds" in data
    assert "ashby_seeds" in data
    assert "total_db_company_slugs" in data

