"""Contract tests for Sarathi Browser Extension API backend integration.

Validates that request and response payloads adhere to the exact schemas
expected by the MV3 extension (background.js and content.js).
"""

import json
import os
import uuid
from pathlib import Path
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
    user = create_user(email, "secret123", "Contract Tester", tier="pro", is_verified=True, role="admin")
    token = create_access_token({
        "sub": f"user_{user['id']}",
        "user_id": user["id"],
        "id": user["id"],
        "email": email,
        "role": "admin",
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

    @patch("src.ai.matcher.get_gemini_client")
    def test_ai_form_autofill_sanitizes_numbers_from_names_and_cleans_address(self, mock_client_fn, client, auth_headers):
        headers, _ = auth_headers

        mock_client = MagicMock()
        mock_resp = MagicMock()
        # Simulate LLM hallucinating numbers in name and street into postal code
        mock_resp.text = """{
            "resolutions": [
                {
                    "field_id": "fn",
                    "semantic_intent": "first_name",
                    "action": "set_value",
                    "value": "Toyanath 146",
                    "confidence": 0.95
                },
                {
                    "field_id": "plz",
                    "semantic_intent": "postal_code",
                    "action": "set_value",
                    "value": "Kerckhoff Str. 146",
                    "confidence": 0.95
                },
                {
                    "field_id": "city",
                    "semantic_intent": "city",
                    "action": "set_value",
                    "value": "Kerckhoff Str. 146",
                    "confidence": 0.95
                },
                {
                    "field_id": "ext",
                    "semantic_intent": "extension",
                    "action": "set_value",
                    "value": "+4915906377419",
                    "confidence": 0.95
                }
            ]
        }"""
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_fn.return_value = mock_client

        payload = {
            "url": "https://mesalvo.wd103.myworkdayjobs.com/apply",
            "company": "Mesalvo",
            "position": "Software Engineer",
            "description": "Dev",
            "fields": [
                {"field_id": "fn", "label": "Vorname*", "type": "text", "tag": "input"},
                {"field_id": "plz", "label": "Postleitzahl", "type": "text", "tag": "input"},
                {"field_id": "city", "label": "Ort", "type": "text", "tag": "input"},
                {"field_id": "ext", "label": "Durchwahl", "type": "text", "tag": "input"},
            ],
        }

        resp = client.post("/api/ai-form-autofill", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        res_map = {r["field_id"]: r for r in data["resolutions"]}

        # Name must be stripped of all digits
        assert res_map["fn"]["value"] == "Toyanath"
        # Postal code must be postal code digits, never street address
        assert res_map["plz"]["value"] == "45144"
        # City must be Essen, never street address
        assert res_map["city"]["value"] == "Essen"
        # Phone extension must NOT receive full phone number
        assert res_map["ext"]["action"] == "skip"
        assert res_map["ext"]["value"] is None


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


class TestExtensionAssetConformity:
    def test_extension_liquid_glass_css_tokens(self):
        import pathlib
        popup_css = pathlib.Path("extension/popup.css").read_text()
        content_css = pathlib.Path("extension/content.css").read_text()
        assert "#07090e" in popup_css or "rgba(7, 9, 14" in popup_css
        assert "blur(" in content_css
        assert "sarathi-floating-pill" in content_css
        assert "rgba(56, 189, 248" in content_css or "#38bdf8" in content_css

    def test_popup_simplify_structure_and_no_legacy_placeholders(self):
        import pathlib
        popup_html = pathlib.Path("extension/popup.html").read_text()
        # Verify modern Simplify-style elements are present
        assert "job-card" in popup_html
        assert "btn-hero" in popup_html
        assert "doc-card-resume" in popup_html
        assert "doc-card-cover" in popup_html
        assert "Autofill This Page" in popup_html

        # Verify legacy useless features are completely purged
        assert "master_cv.pdf" not in popup_html
        assert "btn-copy-filename" not in popup_html
        assert "btn-copy-cv-name" not in popup_html

    def test_workday_url_canonicalization_and_lookup(self, client, auth_headers, monkeypatch):
        import pandas as pd
        import src.dashboard.routers.tracker as tracker_mod
        from src.dashboard.routers.tracker import _canonical_job_url
        headers, _ = auth_headers

        live_url = "https://mesalvo.wd103.myworkdayjobs.com/de-DE/Mesalvo/job/Remote%2C-Germany/Software-Engineer---Medication--w-m-d-_JR100166/apply/applyManually"
        stored_url = "https://mesalvo.wd103.myworkdayjobs.com/de-DE/Mesalvo/job/Remote-Germany/Software-Engineer---Medication--w-m-d-_JR100166"

        canon_live = _canonical_job_url(live_url)
        canon_stored = _canonical_job_url(stored_url)
        assert canon_live == canon_stored
        assert "/apply" not in canon_live

        # Ensure isolated dummy application files exist on disk for CI environments
        test_dir = os.path.join(os.getcwd(), "applications", "2026-11-17")
        os.makedirs(test_dir, exist_ok=True)
        cv_mock = os.path.join(test_dir, "mesalvo_software-engineer-medi_cv.pdf")
        cov_mock = os.path.join(test_dir, "mesalvo_software-engineer-medi_cover.pdf")
        cv_rel = "applications/2026-11-17/mesalvo_software-engineer-medi_cv.pdf"
        cov_rel = "applications/2026-11-17/mesalvo_software-engineer-medi_cover.pdf"
        meta_mock = os.path.join(test_dir, "mesalvo_software-engineer-medi.meta.json")
        for p in (cv_mock, cov_mock):
            if not os.path.isfile(p):
                with open(p, "wb") as f:
                    f.write(b"%PDF-1.4 test")
        with open(meta_mock, "w", encoding="utf-8") as f:
            json.dump({"company": "Mesalvo", "job_url": stored_url, "cv_path": cv_rel, "cover_path": cov_rel}, f)

        mock_crm = pd.DataFrame([{
            "company": "Mesalvo GmbH",
            "position": "Software Engineer - Medication (w/m/d)",
            "job_url": stored_url,
            "status": "Prepared",
            "cv_pdf_path": "applications/2026-11-17/mesalvo_software-engineer-medi_cv.pdf",
            "cover_pdf_path": "applications/2026-11-17/mesalvo_software-engineer-medi_cover.pdf",
        }])
        monkeypatch.setattr(tracker_mod, "load_tracker_df", lambda *args, **kwargs: mock_crm)

        # Lookup by live Workday URL matches CRM and provides both CV and Cover paths
        resp = client.get("/api/applications/lookup", params={"url": live_url}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert "Mesalvo" in data["company"]
        assert "mesalvo_software-engineer-medi_cv.pdf" in data["cv_filename"]
        assert "mesalvo_software-engineer-medi_cover.pdf" in data["cover_filename"]

    def test_content_script_autofill_semantic_guards(self):
        content_path = os.path.join(os.path.dirname(__file__), "..", "extension", "content.js")
        with open(content_path, "r", encoding="utf-8") as f:
            js = f.read()

        # 1. Strict semantic type guards in setNativeValue
        assert "isNameField" in js
        assert "value.replace(/[0-9]/g, \"\").trim()" in js
        assert "isPostalField" in js
        assert "isCityField" in js
        assert "isExtField" in js

        # 2. sarathi-auto-filled marking
        assert "sarathi-auto-filled" in js
        assert "dataset.sarathiFilled" in js

        # 3. Extension guard in phone matching
        assert "extension" in js
        assert "durchwahl" in js

        # 4. Zero auxControls ReferenceError in copilot
        assert "auxControls" not in js

        # 5. Core ATS profile extensions
        assert "deutsch" in js
        assert "englisch" in js
        assert "kündigung" in js
        assert "anrede" in js

        # 6. Multi-user safety: driver's license must NEVER be hardcoded
        assert "führerschein" not in js
        assert "driving license" not in js
        assert "klasse b" not in js

    def test_extension_manifest_and_popup_version_consistency(self):
        import pathlib
        manifest = json.loads(pathlib.Path("extension/manifest.json").read_text())
        popup_html = pathlib.Path("extension/popup.html").read_text()

        # Version matches
        version = manifest["version"]
        assert f"v{version}" in popup_html

        # Web accessible resources whitelists all URLs for extension icons
        war = manifest.get("web_accessible_resources", [])
        assert len(war) > 0
        assert "<all_urls>" in war[0].get("matches", [])

    def test_company_lookup_disk_fallback_when_crm_empty(self, client, auth_headers, monkeypatch):
        import pandas as pd
        import src.dashboard.routers.tracker as tracker_mod
        headers, _ = auth_headers

        # Ensure isolated dummy application files exist on disk for CI environments
        test_dir = os.path.join(os.getcwd(), "applications", "2026-11-17")
        os.makedirs(test_dir, exist_ok=True)
        cv_mock = os.path.join(test_dir, "mesalvo_software-engineer-medi_cv.pdf")
        cov_mock = os.path.join(test_dir, "mesalvo_software-engineer-medi_cover.pdf")
        cv_rel = "applications/2026-11-17/mesalvo_software-engineer-medi_cv.pdf"
        cov_rel = "applications/2026-11-17/mesalvo_software-engineer-medi_cover.pdf"
        meta_mock = os.path.join(test_dir, "mesalvo_software-engineer-medi.meta.json")
        for p in (cv_mock, cov_mock):
            if not os.path.isfile(p):
                with open(p, "wb") as f:
                    f.write(b"%PDF-1.4 test")
        with open(meta_mock, "w", encoding="utf-8") as f:
            json.dump({"company": "Mesalvo", "job_url": "https://mesalvo.wd103.myworkdayjobs.com/de-DE/Mesalvo/job/Remote-Germany/Software-Engineer---Medication--w-m-d-_JR100166", "cv_path": cv_rel, "cover_path": cov_rel}, f)

        # Even if CRM table has 0 rows or unknown job_url
        monkeypatch.setattr(tracker_mod, "load_tracker_df", lambda *args, **kwargs: pd.DataFrame())

        # 1. Lookup by company name directly resolved from applications disk
        resp = client.get("/api/applications/lookup", params={"company": "Mesalvo"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert "mesalvo" in data["cv_filename"].lower()
        assert "mesalvo" in data["cover_filename"].lower()

        # 2. Lookup by live ATS URL with company slug in host/path resolved from disk
        live_workday = "https://mesalvo.wd103.myworkdayjobs.com/de-DE/Mesalvo/job/Remote%2C-Germany/Software-Engineer---Medication--w-m-d-_JR100166/apply"
        resp_url = client.get("/api/applications/lookup", params={"url": live_workday}, headers=headers)
        assert resp_url.status_code == 200
        data_url = resp_url.json()
        assert data_url["found"] is True
        assert "mesalvo" in data_url["cv_filename"].lower()

