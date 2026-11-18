"""Tests for Resume Upload Auto-Tune and Filter Rules Persistence."""

import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, get_user_filter_rules, get_user_profile


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_user():
    unique_email = f"autotune_{uuid.uuid4().hex[:8]}@example.com"
    user = create_user(unique_email, "secret123", "AutoTune User", tier="pro")
    token = create_access_token({"sub": f"user_{user['id']}", "user_id": user["id"], "id": user["id"], "role": "candidate"})
    return {"Authorization": f"Bearer {token}"}, user


def test_resume_upload_automatically_tunes_and_persists_filter_rules(client, auth_user):
    headers, user = auth_user
    fake_pdf = b"%PDF-1.4 test resume content"

    mock_profile = {
        "personal_info": {"name": "Alex Bau", "location": "Berlin, Germany"},
        "education": [{"degree": "M.Sc. Civil Engineering", "university": "TU Berlin"}],
        "experience": [{"role": "Structural Engineer", "company": "Zublin AG", "description": "Statik and BIM"}],
        "skills": {"Civil": ["Statik", "AutoCAD", "BIM"]},
        "languages": {"German": "B2", "English": "C1"},
        "target_titles": ["Bauingenieur", "Tragwerksplaner"],
    }
    mock_rules = {
        "discipline": "Civil Engineering",
        "target_titles": ["Bauingenieur", "Tragwerksplaner", "Statiker"],
        "inclusion_keywords": ["Statik", "AutoCAD", "BIM"],
        "exclusion_keywords": ["Dachdecker", "Maler"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 1,
        "max_years_experience": 3,
        "summary": "Civil engineer.",
    }

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=mock_profile), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=mock_rules):

        resp = client.post(
            "/api/profile/parse-resume",
            files={"file": ("alex_cv.pdf", fake_pdf, "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "filter_rules" in data
        assert data["filter_rules"]["discipline"] == "Civil Engineering"
        assert "Bauingenieur" in data["filter_rules"]["target_titles"]

        # Verify DB persistence
        saved_rules = get_user_filter_rules(user["id"])
        assert saved_rules["discipline"] == "Civil Engineering"
        assert "Bauingenieur" in saved_rules["target_titles"]


def test_resume_upload_guest_user_returns_autotuned_rules_without_crashing(client):
    fake_pdf = b"%PDF-1.4 test guest resume content"
    mock_profile = {
        "personal_info": {"name": "Guest Engineer"},
        "education": [],
        "experience": [],
        "skills": {},
    }
    mock_rules = {
        "discipline": "General Engineering",
        "target_titles": ["Ingenieur", "Project Engineer"],
        "inclusion_keywords": ["Engineering"],
        "exclusion_keywords": ["Call Center"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": "Guest profile.",
    }

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=mock_profile), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=mock_rules):

        resp = client.post(
            "/api/profile/parse-resume",
            files={"file": ("guest_cv.pdf", fake_pdf, "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "filter_rules" in data
        assert data["filter_rules"]["discipline"] == "General Engineering"
