"""Contract tests for Sarathi Browser Extension API backend integration.

Validates that request and response payloads adhere to the exact schemas
expected by the MV3 extension (background.js and content.js).
"""

import uuid
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"contract_tester_{unique_suffix}@example.com"
    user = create_user(email, "secret123", "Contract Tester", tier="pro", is_verified=True)
    token = create_access_token({
        "sub": f"user_{user['id']}",
        "user_id": user["id"],
        "id": user["id"],
        "email": email,
        "role": "candidate",
    })
    return {"Authorization": f"Bearer {token}"}, user


class TestExtensionAuthContract:
    def test_unauthenticated_requests_rejected(self, client):
        # Missing auth header on strictly protected endpoints returns 401
        resp = client.post("/api/ai-form-autofill", json={})
        assert resp.status_code == 401

        # Invalid bearer token on JWT-validated endpoints returns 401
        resp = client.post(
            "/api/answer-form-question",
            headers={"Authorization": "Bearer invalid_token"},
            json={"question": "Why work here?"},
        )
        assert resp.status_code == 401

        resp = client.get(
            "/api/profile/custom-fields",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert resp.status_code == 401


class TestExtensionLookupContract:
    def test_lookup_schema_when_not_found(self, client, auth_headers):
        headers, _ = auth_headers
        resp = client.get("/api/applications/lookup?url=https://unknown-portal.com/job/999", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "found" in data
        assert data["found"] is False


class TestExtensionAiAutofillContract:
    @patch("src.ai.matcher.get_gemini_client")
    def test_ai_form_autofill_success_contract(self, mock_client_fn, client, auth_headers):
        headers, _ = auth_headers

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = """{
            "resolutions": [
                {
                    "field_id": "first_name",
                    "action": "set_value",
                    "value": "Toyanath",
                    "confidence": 0.98,
                    "reasoning": "Standard given name from candidate profile"
                },
                {
                    "field_id": "country_select",
                    "action": "select_option",
                    "value": "Germany",
                    "confidence": 0.95,
                    "reasoning": "Candidate residence country"
                },
                {
                    "field_id": "cv_upload",
                    "action": "attach_document",
                    "value": "cv",
                    "semantic_intent": "cv",
                    "confidence": 0.99,
                    "reasoning": "Primary curriculum vitae file input"
                }
            ]
        }"""
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_fn.return_value = mock_client

        payload = {
            "url": "https://boards.greenhouse.io/testco/jobs/12345",
            "company": "TestCo",
            "position": "Software Engineer",
            "description": "We are seeking a Python developer.",
            "fields": [
                {
                    "field_id": "first_name",
                    "label": "First Name",
                    "type": "text",
                    "tag": "input",
                    "required": True,
                },
                {
                    "field_id": "country_select",
                    "label": "Country",
                    "type": "combobox",
                    "tag": "select",
                    "options": ["Germany", "United States", "United Kingdom"],
                },
                {
                    "field_id": "cv_upload",
                    "label": "Resume / CV",
                    "type": "file",
                    "tag": "input",
                },
            ],
        }

        resp = client.post("/api/ai-form-autofill", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["success"] is True
        assert "resolutions" in data
        assert isinstance(data["resolutions"], list)
        assert len(data["resolutions"]) == 3

        r0 = data["resolutions"][0]
        assert r0["field_id"] == "first_name"
        assert r0["action"] == "set_value"
        assert r0["value"] == "Toyanath"
        assert isinstance(r0["confidence"], (int, float))

        r2 = data["resolutions"][2]
        assert r2["field_id"] == "cv_upload"
        assert r2["action"] == "attach_document"


class TestExtensionCopilotContract:
    @patch("src.ai.matcher.get_gemini_client")
    def test_answer_form_question_contract(self, mock_client_fn, client, auth_headers):
        headers, _ = auth_headers

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Ich habe fundierte Kenntnisse in Python und Docker."
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_fn.return_value = mock_client

        payload = {
            "question": "Bitte beschreiben Sie Ihre Programmiererfahrung.",
            "company": "Example GmbH",
            "language": "de",
        }
        resp = client.post("/api/answer-form-question", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "answer" in data
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0


class TestExtensionSeedDiscoveryContract:
    @patch("src.dashboard.routers.seeds.append_slug_to_seed")
    def test_seed_discover_contract(self, mock_append, client, auth_headers):
        headers, _ = auth_headers
        mock_append.return_value = True

        payload = {
            "url": "https://jobs.lever.co/examplecorp/frontend-engineer",
            "ats_type": "lever",
            "slug": "examplecorp",
            "company": "ExampleCorp",
            "source": "extension_preview",
        }
        resp = client.post("/api/seeds/discover", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["slug"] == "examplecorp"
        assert data["ats_type"] == "lever"
        assert data["added"] is True


class TestExtensionLearnedFieldsContract:
    def test_custom_fields_lifecycle_contract(self, client, auth_headers):
        headers, _ = auth_headers

        # 1. Save learned fields
        save_resp = client.post(
            "/api/profile/custom-fields",
            json={"fields": {"notice_period": "3 months", "preferred_ide": "Neovim"}},
            headers=headers,
        )
        assert save_resp.status_code == 200
        save_data = save_resp.json()
        assert save_data["success"] is True
        assert save_data["count"] >= 2

        # 2. Get learned fields
        get_resp = client.get("/api/profile/custom-fields", headers=headers)
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert "fields" in get_data
        assert get_data["fields"].get("notice_period") == "3 months"

        # 3. Clear learned fields
        del_resp = client.delete("/api/profile/custom-fields", headers=headers)
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["success"] is True

        # 4. Verify empty after clear
        verify_resp = client.get("/api/profile/custom-fields", headers=headers)
        assert verify_resp.status_code == 200
        assert verify_resp.json()["fields"] == {}
