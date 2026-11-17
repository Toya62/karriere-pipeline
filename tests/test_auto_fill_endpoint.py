import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from src.dashboard.app import create_app

client = TestClient(create_app())


def test_autofill_missing_url():
    resp = client.post("/api/applications/auto-fill", json={})
    assert resp.status_code == 400
    assert "Missing job_url" in resp.json()["error"]


@patch("src.automation.form_filler.ATSFormFiller.fill_application", new_callable=AsyncMock)
def test_autofill_success_mocked(mock_fill):
    mock_fill.return_value = {
        "platform": "personio",
        "filled_fields": [{"field": "First Name", "value": "Toyanath"}],
        "attached_files": [{"type": "CV", "file": "cv.pdf"}],
        "screenshot_base64": "dummy",
        "status": "ready_for_review"
    }

    payload = {
        "company": "meteocontrol GmbH",
        "position": "OT Security Engineer",
        "job_url": "https://meteocontrol.jobs.personio.de/job/2867312",
        "headed": False
    }

    resp = client.post("/api/applications/auto-fill", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["platform"] == "personio"
    assert len(data["filled_fields"]) == 1
    assert len(data["attached_files"]) == 1


def test_application_lookup_empty_query(tmp_path, monkeypatch):
    import src.dashboard.routers.tracker as tracker_mod

    # 1. When master CV file exists on disk
    fake_master = tmp_path / "master_cv.pdf"
    fake_master.write_bytes(b"%PDF-1.4 dummy")
    monkeypatch.setattr(tracker_mod, "MASTER_CV_REL", str(fake_master))

    resp = client.get("/api/applications/lookup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert data["is_tailored"] is False
    assert "master_cv.pdf" in data["cv_filename"]
    assert "master_cv.pdf" in data["cv_path"]
    assert data["cover_path"] is None or data["cover_path"] == ""
    assert "extra_documents" in data

    # 2. When master CV file does not exist
    monkeypatch.setattr(tracker_mod, "MASTER_CV_REL", str(tmp_path / "nonexistent.pdf"))
    resp_empty = client.get("/api/applications/lookup")
    assert resp_empty.status_code == 200
    data_empty = resp_empty.json()
    assert data_empty["found"] is False
    assert data_empty["cv_filename"] == ""
    assert data_empty["cv_path"] == ""


def test_custom_fields_lifecycle(tmp_path, monkeypatch):
    import uuid
    from src.db.database import update_user
    from src.core.security import create_access_token
    email = f"autofill_{uuid.uuid4().hex[:8]}@test.com"
    reg = client.post("/api/auth/register", json={"email": email, "password": "password123!", "full_name": "Auto Fill"})
    user_id = reg.json()["user"]["id"]
    update_user(user_id, {"is_verified": True})
    token = create_access_token({"user_id": user_id, "email": email, "role": "candidate"})
    headers = {"Authorization": f"Bearer {token}"}

    test_json = tmp_path / "learned_fields.json"
    from src.dashboard.routers import jobs
    monkeypatch.setattr(jobs, "LEARNED_FIELDS_PATH", str(test_json))

    # 1. Get initially empty
    resp = client.get("/api/profile/custom-fields", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["fields"] == {}

    # 2. Save new fields
    payload = {
        "fields": {
            "driver license": "Class B",
            "notice period": "1 month"
        }
    }
    resp = client.post("/api/profile/custom-fields", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["count"] == 2

    # 3. Read back
    resp = client.get("/api/profile/custom-fields", headers=headers)
    assert resp.status_code == 200
    fields = resp.json()["fields"]
    assert fields["driver license"] == "Class B"
    assert fields["notice period"] == "1 month"


def test_application_lookup_with_referrer_walk(tmp_path, monkeypatch):
    import os
    import pandas as pd
    import src.dashboard.routers.tracker as tracker_mod

    # Create dummy CV and cover letter in a subdirectory inside cwd
    test_apps_dir = os.path.join(os.getcwd(), "applications", "test_referrer_walk")
    os.makedirs(test_apps_dir, exist_ok=True)
    fake_cv = os.path.join(test_apps_dir, "Acme_CV.pdf")
    fake_cover = os.path.join(test_apps_dir, "Acme_Anschreiben.pdf")
    with open(fake_cv, "wb") as f:
        f.write(b"%PDF-1.4 dummy cv")
    with open(fake_cover, "wb") as f:
        f.write(b"%PDF-1.4 dummy cover")

    rel_cv = os.path.relpath(fake_cv, os.getcwd())
    rel_cover = os.path.relpath(fake_cover, os.getcwd())

    mock_crm = pd.DataFrame([{
        "company": "Acme Corp",
        "position": "Software Engineer",
        "job_url": "https://www.linkedin.com/jobs/view/99887766/",
        "status": "Prepared",
        "cv_pdf_path": rel_cv,
        "cover_pdf_path": rel_cover,
    }])

    monkeypatch.setattr(tracker_mod, "load_tracker_df", lambda *args, **kwargs: mock_crm)

    try:
        # 1. Final ATS form URL doesn't match CRM directly, but referrer is the stored LinkedIn job_url
        resp = client.get("/api/applications/lookup", params={
            "url": "https://jobs.ashbyhq.com/acme/apply/step-2",
            "referrer": "https://www.linkedin.com/jobs/view/99887766/",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["is_tailored"] is True
        assert data["company"] == "Acme Corp"
        assert data["position"] == "Software Engineer"
        assert data["cv_filename"] == "Acme_CV.pdf"
        assert data["cover_filename"] == "Acme_Anschreiben.pdf"

        # 2. When neither URL nor referrer match CRM
        resp_miss = client.get("/api/applications/lookup", params={
            "url": "https://jobs.ashbyhq.com/otherco/apply",
            "referrer": "https://google.com/",
        })
        assert resp_miss.status_code == 200
        data_miss = resp_miss.json()
        assert data_miss["found"] is False
        assert data_miss["is_tailored"] is False
    finally:
        # Cleanup test files
        if os.path.exists(fake_cv):
            os.remove(fake_cv)
        if os.path.exists(fake_cover):
            os.remove(fake_cover)
        if os.path.exists(test_apps_dir):
            os.rmdir(test_apps_dir)




