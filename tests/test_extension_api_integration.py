"""Tests for the Sarathi Browser Extension API backend integration."""

import uuid
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, get_db_connection, is_postgres


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def extension_user_and_headers():
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"extension_{unique_suffix}@example.com"
    u = create_user(email, "password123", "Extension Tester", tier="pro", is_verified=True)
    user_id = u["id"]

    token = create_access_token({
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "id": user_id,
        "email": email,
        "role": "candidate",
    })
    return {"id": user_id, "email": email}, {"Authorization": f"Bearer {token}"}


def test_extension_application_lookup(test_client):
    # Lookup without parameters returns found: False
    resp = test_client.get("/api/applications/lookup")
    assert resp.status_code == 200
    data = resp.json()
    assert "found" in data


@patch("src.dashboard.routers.seeds.append_slug_to_seed")
def test_extension_seed_discovery(mock_append, test_client):
    mock_append.return_value = True
    payload = {
        "url": "https://careers.example.com/jobs/123",
        "ats_type": "greenhouse",
        "slug": f"test-company-{uuid.uuid4().hex[:6]}",
        "company": "Test Company",
        "source": "extension",
    }
    resp = test_client.post("/api/seeds/discover", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_extension_profile_and_custom_fields(test_client, extension_user_and_headers):
    user, headers = extension_user_and_headers

    # 1. Fetch profile
    resp_prof = test_client.get("/api/profile", headers=headers)
    assert resp_prof.status_code == 200
    pdata = resp_prof.json()
    assert "personal_info" in pdata

    # 2. Save learned custom fields
    save_payload = {
        "fields": {
            "notice_period_days": "30",
            "preferred_work_mode": "Hybrid",
        }
    }
    resp_save = test_client.post("/api/profile/custom-fields", json=save_payload, headers=headers)
    assert resp_save.status_code == 200

    # 3. Read back learned custom fields
    resp_get = test_client.get("/api/profile/custom-fields", headers=headers)
    assert resp_get.status_code == 200
    gdata = resp_get.json()
    assert "fields" in gdata
    assert gdata["fields"]["notice_period_days"] == "30"


@patch("src.ai.matcher.get_gemini_client")
def test_extension_copilot_endpoint(mock_client_fn, test_client, extension_user_and_headers):
    user, headers = extension_user_and_headers

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Ich habe umfassende praktische Erfahrung mit Python und Docker aus meiner Tätigkeit bei Bosch Engineering."
    mock_client.models.generate_content.return_value = mock_resp
    mock_client_fn.return_value = mock_client

    payload = {
        "question": "Welche Erfahrungen haben Sie mit Python?",
        "company": "Bosch",
        "language": "de",
    }
    resp = test_client.post("/api/answer-form-question", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Bosch Engineering" in data["answer"]
