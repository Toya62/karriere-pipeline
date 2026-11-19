"""Integration test for Multi-Tenant Candidate Profile API.

Ensures strict user isolation between tenants and verifies that regular users
never receive admin disk facts, with full support for custom languages and demographics.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, save_user_profile


@pytest.fixture
def client():
    return TestClient(app)


def make_user(email_prefix: str, role: str = "candidate"):
    unique = uuid.uuid4().hex[:8]
    email = f"{email_prefix}_{unique}@example.com"
    user = create_user(email, "password123", f"{email_prefix.capitalize()} Name", tier="free", is_verified=True)
    token = create_access_token({
        "sub": f"user_{user['id']}",
        "user_id": user["id"],
        "id": user["id"],
        "email": email,
        "role": role,
    })
    return {"Authorization": f"Bearer {token}"}, user


def test_multi_tenant_profile_isolation(client):
    # 1. Create two distinct users
    headers_a, user_a = make_user("alice")
    headers_b, user_b = make_user("bob")

    # 2. Save Alice's profile (French native, Female, UX Designer)
    alice_profile = {
        "personal_info": {
            "name": "Alice Martin",
            "email": user_a["email"],
            "gender": "female",
            "salutation": "Ms.",
            "pronouns": "she/her",
            "location": "Paris, France",
        },
        "languages": {
            "French": "Native",
            "English": "C1",
        },
        "job_search_preferences": {
            "notice_period": "1 month",
            "travel_readiness": "Up to 10%",
        },
    }
    put_a = client.put("/api/profile", json=alice_profile, headers=headers_a)
    assert put_a.status_code == 200
    assert put_a.json()["success"] is True

    # 3. Save Bob's profile (German B2, Male, DevOps)
    bob_profile = {
        "personal_info": {
            "name": "Bob Schmidt",
            "email": user_b["email"],
            "gender": "male",
            "salutation": "Herr",
            "pronouns": "he/him",
            "location": "Berlin, Germany",
        },
        "languages": {
            "German": "B2",
            "English": "Fluent",
        },
        "job_search_preferences": {
            "notice_period": "3 months",
        },
    }
    post_b = client.post("/api/profile", json=bob_profile, headers=headers_b)
    assert post_b.status_code in (200, 201)
    assert post_b.json()["success"] is True

    # 4. Fetch Alice's profile -> Verify zero Bob facts, zero Toyanath Pandey admin facts
    res_a = client.get("/api/profile", headers=headers_a)
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["user_id"] == user_a["id"]
    assert data_a["has_profile"] is True
    assert data_a["personal_info"]["name"] == "Alice Martin"
    assert data_a["personal_info"]["gender"] == "female"
    assert data_a["languages"]["French"] == "Native"
    assert "Bob" not in str(data_a)
    assert "Toyanath" not in str(data_a)
    assert "Kerckhoff" not in str(data_a)

    # 5. Fetch Bob's profile -> Verify zero Alice facts
    res_b = client.get("/api/profile", headers=headers_b)
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["user_id"] == user_b["id"]
    assert data_b["has_profile"] is True
    assert data_b["personal_info"]["name"] == "Bob Schmidt"
    assert data_b["personal_info"]["gender"] == "male"
    assert data_b["languages"]["German"] == "B2"
    assert "Alice" not in str(data_b)
    assert "Toyanath" not in str(data_b)


def test_multi_tenant_lookup_application_no_disk_leakage(client):
    """Ensure non-admin SaaS tenants cannot see admin's on-disk application files."""
    headers_cand, user_cand = make_user("stranger", role="candidate")
    assert user_cand["id"] > 1

    # Attempt to lookup a company that only exists on admin server disk (e.g. Mesalvo)
    res = client.get("/api/applications/lookup?company=Mesalvo", headers=headers_cand)
    assert res.status_code == 200
    data = res.json()
    # For a tenant who hasn't applied to Mesalvo, found must be False (zero disk file leakage)
    assert data["found"] is False
    assert "extra_documents" not in data or data["extra_documents"] == {}


def test_multi_tenant_ai_form_resolver_no_essen_fallback():
    """Verify AI Form Resolver uses dynamic tenant profile facts and never hardcodes Essen/45144."""
    import json
    from unittest.mock import MagicMock, patch
    from src.ai.form_resolver import resolve_form_fields

    tenant_profile = {
        "personal_info": {
            "name": "Clara Schumann",
            "city": "München",
            "postal_code": "80331",
            "location": "Marienplatz 1, 80331 München",
            "gender": "female",
            "salutation": "Frau",
            "pronouns": "sie/ihr",
        },
        "languages": {
            "German": "Native",
            "English": "C2",
        },
        "job_search_preferences": {
            "notice_period": "1 month",
            "expected_salary": "75.000 €",
            "travel_readiness": "None",
        },
    }

    fields = [
        {"field_id": "f_zip", "id": "postal_code", "label": "PLZ / Postleitzahl", "name": "plz", "tag": "input"},
        {"field_id": "f_city", "id": "city", "label": "Wohnort / Stadt", "name": "city", "tag": "input"},
        {"field_id": "f_name", "id": "first_name", "label": "Vorname", "name": "vorname", "tag": "input"},
    ]

    # Simulate raw LLM hallucinating street info into postal/city fields
    mock_llm_payload = json.dumps({
        "resolutions": [
            {
                "field_id": "f_zip",
                "semantic_intent": "postal_code",
                "action": "set_value",
                "value": "Leopoldstraße 10",  # contains street, no 5 digits -> should sanitize to cand_postal
                "selected_option_index": None,
                "confidence": 0.9,
                "reasoning": "Postal code",
            },
            {
                "field_id": "f_city",
                "semantic_intent": "city",
                "action": "set_value",
                "value": "Maximilianstraße 12",  # contains street word -> should sanitize to cand_city
                "selected_option_index": None,
                "confidence": 0.9,
                "reasoning": "City",
            },
            {
                "field_id": "f_name",
                "semantic_intent": "first_name",
                "action": "set_value",
                "value": "Clara 99",  # contains digits -> should sanitize to pure letters
                "selected_option_index": None,
                "confidence": 0.95,
                "reasoning": "Name",
            },
        ]
    })

    mock_resp = MagicMock()
    mock_resp.text = mock_llm_payload

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    with patch("src.ai.matcher.get_gemini_client", return_value=mock_client):
        result = resolve_form_fields(
            fields=fields,
            job_context={"company": "Munich Tech GmbH", "position": "Senior Architect", "description": "Cloud platform"},
            candidate_profile=tenant_profile,
            candidate_name="Clara Schumann",
        )

        assert result["success"] is True
        res_by_id = {r["field_id"]: r for r in result["resolutions"]}

        # 1. Postal code must be Clara's postal code (80331), NOT Essen (45144)
        assert res_by_id["f_zip"]["value"] == "80331"

        # 2. City must be Clara's city (München), NOT Essen
        assert res_by_id["f_city"]["value"] == "München"

        # 3. First name must have digits stripped
        assert res_by_id["f_name"]["value"] == "Clara"

        # 4. Verify prompt sent to Gemini has ZERO Essen, 45144, or Toyanath references
        call_args = mock_client.models.generate_content.call_args
        prompt_sent = call_args.kwargs["contents"]
        assert "Essen" not in prompt_sent
        assert "45144" not in prompt_sent
        assert "Toyanath" not in prompt_sent
        assert "Clara Schumann" in prompt_sent
        assert "München" in prompt_sent


