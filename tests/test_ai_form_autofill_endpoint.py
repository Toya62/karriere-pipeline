import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from src.dashboard.app import create_app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, setup_db

@pytest.fixture
def client():
    setup_db()
    app = create_app()
    return TestClient(app)

@pytest.fixture
def auth_headers():
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"autofill_{unique_suffix}@example.com"
    u = create_user(email, "password123", "Autofill Tester", tier="pro", is_verified=True)
    user_id = u["id"]
    token = create_access_token({
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "id": user_id,
        "email": email,
        "role": "candidate",
    })
    return {"Authorization": f"Bearer {token}"}

def test_ai_form_autofill_endpoint_unauthorized(client):
    resp = client.post("/api/ai-form-autofill", json={"fields": []})
    assert resp.status_code == 401

def test_ai_form_autofill_endpoint_success(client, auth_headers):
    mock_resolutions = {
        "success": True,
        "resolutions": [
            {
                "field_id": "f_1",
                "semantic_intent": "email",
                "action": "set_value",
                "value": "pandeytoya22@gmail.com",
                "selected_option_index": None,
                "confidence": 1.0,
                "reasoning": "Candidate email"
            }
        ],
        "fields_count": 1,
        "resolved_count": 1,
        "error": None
    }
    with patch("src.ai.form_resolver.resolve_form_fields", return_value=mock_resolutions):
        resp = client.post(
            "/api/ai-form-autofill",
            headers=auth_headers,
            json={
                "url": "https://jobs.lever.co/example",
                "company": "Neural Frames",
                "position": "Backend SWE",
                "fields": [{"field_id": "f_1", "tag": "input", "label": "Email", "type": "email"}]
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["resolutions"]) == 1
        assert data["resolutions"][0]["value"] == "pandeytoya22@gmail.com"
