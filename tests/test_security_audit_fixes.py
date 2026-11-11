import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, setup_db
from src.core.security import verify_google_id_token, get_jwks_client
from src.generators.compiler import compile_all_applications

@pytest.fixture(scope="module")
def app_instance():
    setup_db()
    return create_app()

@pytest.fixture
def client(app_instance):
    return TestClient(app_instance)

@pytest.fixture
def auth_headers():
    unique_email = f"sec_test_{uuid.uuid4().hex[:8]}@example.com"
    u = create_user(unique_email, "pass123", "Sec Tester", tier="pro", is_verified=True)
    user_id = u["id"]
    token = create_access_token({
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "id": user_id,
        "email": unique_email,
        "role": "candidate",
    })
    return {"Authorization": f"Bearer {token}"}

def test_scraper_command_injection_rejected(client, auth_headers):
    resp = client.post(
        "/api/run-scraper",
        headers=auth_headers,
        json={"portal": "linkedin; rm -rf /", "days": 1}
    )
    assert resp.status_code == 400
    assert "Invalid portal" in resp.json()["error"]

def test_scraper_invalid_days_rejected(client, auth_headers):
    resp = client.post(
        "/api/run-scraper",
        headers=auth_headers,
        json={"portal": "linkedin", "days": 9999}
    )
    assert resp.status_code == 400
    assert "Days must be an integer between 1 and 30" in resp.json()["error"]

def test_matcher_command_injection_rejected(client, auth_headers):
    resp = client.post(
        "/api/run-matcher",
        headers=auth_headers,
        json={"portal": "all && cat /etc/passwd", "max_age_days": 2}
    )
    assert resp.status_code == 400
    assert "Invalid portal" in resp.json()["error"]

def test_matcher_invalid_max_age_rejected(client, auth_headers):
    resp = client.post(
        "/api/run-matcher",
        headers=auth_headers,
        json={"portal": "all", "max_age_days": 100}
    )
    assert resp.status_code == 400
    assert "max_age_days must be an integer between 1 and 30" in resp.json()["error"]

def test_compiler_path_traversal_rejected():
    with pytest.raises(ValueError, match="Invalid target_date format"):
        compile_all_applications(target_date="../../etc")

def test_google_token_verification_requires_client_id(monkeypatch):
    monkeypatch.setattr("src.core.security.GOOGLE_CLIENT_ID", "")
    assert verify_google_id_token("any_token") is None

def test_supabase_jwks_https_enforced(monkeypatch):
    monkeypatch.setattr("src.core.security.SUPABASE_JWKS_URL", "http://insecure-jwks.example.com")
    monkeypatch.setattr("src.core.security._jwks_client", None)
    client = get_jwks_client()
    assert client is None
