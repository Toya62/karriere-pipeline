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
