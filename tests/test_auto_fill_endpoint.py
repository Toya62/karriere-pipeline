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


def test_application_lookup_empty_query():
    resp = client.get("/api/applications/lookup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert data["cv_path"] == ""
    assert data["cover_path"] == ""
    assert data["cv_filename"] == ""
    assert "extra_documents" in data


def test_custom_fields_lifecycle(tmp_path, monkeypatch):
    import uuid
    email = f"autofill_{uuid.uuid4().hex[:8]}@test.com"
    reg = client.post("/api/auth/register", json={"email": email, "password": "password123!", "full_name": "Auto Fill"})
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}

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



