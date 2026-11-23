# tests/test_generation_errors.py
"""Bug #1: AI generation failures must surface, not silently reset.

Backend: a provider failure records a machine-readable `reason` on the
generation status, and the POST endpoint returns 5xx with that reason.
"""
import os

os.environ["DATABASE_URL"] = ""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.applications import classify_generation_error, run_application_generation
from src.dashboard.routers import generation as generation_router
from src.dashboard.routers.auth import create_access_token
from src.dashboard.state import APP_GEN_STATUS
from src.db.database import create_user, setup_db

client = TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    setup_db()
    uid = uuid.uuid4().hex[:8]
    email = f"gen_err_test_{uid}@example.com"
    user = create_user(
        email=email,
        hashed_password="secret123",
        full_name="Generation Error Test User",
        role="candidate",
        tier="pro",
        is_verified=True,
    )
    user_id = user["id"]
    token = create_access_token(data={
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "id": user_id,
        "email": email,
        "role": "candidate",
    })
    return {"Authorization": f"Bearer {token}"}


# --- classifier -----------------------------------------------------------

def test_classify_rate_limited_on_429():
    assert classify_generation_error("Groq error: HTTP 429 Too Many Requests") == "rate_limited"
    assert classify_generation_error("rate limit exceeded, retry later") == "rate_limited"


def test_classify_all_providers_failed_on_router_message():
    msg = ("All AI Router providers failed. Errors: "
           "Gemini(gemini-2.5-flash) error: 503 Service Unavailable; "
           "Groq(llama) error: 503 Service Unavailable")
    assert classify_generation_error(msg) == "all_providers_failed"


def test_classify_provider_unavailable_on_503():
    assert classify_generation_error("Gemini error: 503 Service Unavailable") == "provider_unavailable"
    assert classify_generation_error("model overloaded, try again") == "provider_unavailable"


def test_classify_unknown_error_falls_back_to_error():
    assert classify_generation_error("something unexpected broke") == "error"
    assert classify_generation_error("") == "error"


# --- background worker records the reason ---------------------------------

def test_failed_generation_records_error_status_with_reason(monkeypatch):
    task_key = f"gen_err_{uuid.uuid4().hex[:8]}"
    failure = {
        "success": False,
        "error": ("All AI Router providers failed. Errors: "
                  "Gemini(gemini-2.5-flash) error: 503 Service Unavailable; "
                  "Groq(llama-3.3-70b) error: 429 Too Many Requests"),
    }
    monkeypatch.setattr(
        "src.generators.application.generate_application", lambda **kwargs: failure
    )
    run_application_generation(
        company="Acme", position="Dev", description="x" * 60,
        job_url="https://example.com/jobs/1", location="Berlin",
        language=None, task_key=task_key, user_id=1,
    )
    status = APP_GEN_STATUS[task_key]
    assert status["status"] == "error"
    # A 429 anywhere in the provider breakdown means throttled.
    assert status["reason"] == "rate_limited"
    assert "Gemini" in status["message"]


def test_generation_exception_records_reason(monkeypatch):
    task_key = f"gen_err_{uuid.uuid4().hex[:8]}"

    def _boom(**kwargs):
        raise RuntimeError("All AI Router providers failed. Errors: Gemini error: 503")

    monkeypatch.setattr("src.generators.application.generate_application", _boom)
    run_application_generation(
        company="Acme", position="Dev", description="x" * 60,
        job_url="https://example.com/jobs/1", location="Berlin",
        language=None, task_key=task_key, user_id=1,
    )
    status = APP_GEN_STATUS[task_key]
    assert status["status"] == "error"
    assert status["reason"] == "all_providers_failed"


# --- endpoint returns 5xx with reason --------------------------------------

def test_generate_application_endpoint_returns_5xx_with_reason(monkeypatch, auth_headers):
    def _boom(**kwargs):
        raise RuntimeError(
            "All AI Router providers failed. Errors: "
            "Gemini(gemini-2.5-flash) error: 503 Service Unavailable"
        )

    monkeypatch.setattr(generation_router, "launch_application_generation", _boom)
    res = client.post(
        "/api/generate-application",
        json={
            "company": "Acme",
            "position": "Dev",
            "description": "A sufficiently long job description for ATS tailoring purposes.",
            "job_url": "https://example.com/jobs/1",
            "location": "Berlin",
        },
        headers=auth_headers,
    )
    assert res.status_code == 500
    body = res.json()
    assert body["reason"] == "all_providers_failed"
    assert "503" in body["error"]
