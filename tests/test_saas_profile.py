"""Tests for SaaS profile isolation, resume parsing endpoint, and preferences."""

import io
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.db.database import setup_db


@pytest.fixture
def client():
    setup_db()
    app = create_app()
    return TestClient(app)


def test_guest_profile_is_empty_with_has_profile_false(client):
    """Unauthenticated guest querying /api/profile gets has_profile=False and no Toyanath data."""
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_profile"] is False
    assert data["user_id"] == 0
    assert data["experience"] == []
    assert data["personal_info"]["name"] == ""
    assert "pandeytoya22@gmail.com" not in str(data)


def test_parse_resume_endpoint_rejects_non_pdf(client):
    """Uploading non-pdf or empty file returns 400 Bad Request."""
    files = {"file": ("malicious.exe", b"not a pdf", "application/octet-stream")}
    resp = client.post("/api/profile/parse-resume", files=files)
    assert resp.status_code == 400
    err_msg = resp.json().get("detail") or resp.json().get("error") or ""
    assert "PDF" in err_msg


def test_parse_resume_endpoint_success(client):
    """Uploading valid PDF returns structured candidate profile and recommendations."""
    fake_profile = {
        "personal_info": {
            "name": "Jordan Lee",
            "email": "jordan@example.com",
            "phone": "+49 151 9999999",
            "location": "Stuttgart, Germany",
            "relocation": "Ready to relocate",
            "linkedin": "",
            "github": "",
        },
        "target_titles": ["Embedded Systems Engineer", "Robotics Software Developer"],
        "archetype": "embedded_automotive",
        "experience_summary": "Embedded C++ developer with ROS2 and Linux experience.",
        "education": [{"degree": "B.Sc. Mechatronics", "university": "TU Munich", "graduation_year": "2023", "details": ""}],
        "experience": [{"role": "Robotics Intern", "company": "RoboGmbH", "period": "2023 - 2024", "description": "ROS2 development."}],
        "skills": {"Languages": ["C++", "Python"], "Robotics": ["ROS2", "CAN bus"]},
        "languages": {"Deutsch": "B2", "Englisch": "C1"},
        "recommended_filters": {
            "branch": "Robotics & Embedded Systems",
            "titles": ["Embedded Systems Engineer", "Robotics Developer"],
            "suggested_countries": ["Germany"],
            "default_mode": "hybrid",
        },
    }

    token = create_access_token({"user_id": 88, "email": "jordan@example.com", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=fake_profile):
        files = {"file": ("resume.pdf", b"%PDF-1.4 sample stream...", "application/pdf")}
        resp = client.post("/api/profile/parse-resume", files=files, headers=headers)
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["success"] is True
        assert res_data["has_profile"] is True
        assert res_data["profile"]["personal_info"]["name"] == "Jordan Lee"
        assert "Embedded Systems Engineer" in res_data["profile"]["target_titles"]

    # Verify subsequent GET /api/profile returns the saved profile for this user
    get_resp = client.get("/api/profile", headers=headers)
    assert get_resp.status_code == 200
    profile_data = get_resp.json()
    assert profile_data["has_profile"] is True
    assert profile_data["personal_info"]["name"] == "Jordan Lee"
    assert len(profile_data["experience"]) == 1


def test_save_preferences_endpoint(client):
    """POST /api/profile/preferences persists search criteria for user."""
    token = create_access_token({"user_id": 89, "email": "dev@example.com", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "branch": "Cloud DevOps",
        "titles": ["Cloud Engineer", "DevOps Engineer"],
        "countries": ["Germany", "Switzerland"],
        "cities": ["Berlin", "Munich"],
        "remote": "remote",
    }
    resp = client.post("/api/profile/preferences", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Verify saved
    get_resp = client.get("/api/profile", headers=headers)
    assert get_resp.status_code == 200
    prefs = get_resp.json().get("job_search_preferences", {})
    assert prefs.get("branch") == "Cloud DevOps"
    assert "Switzerland" in prefs.get("countries", [])


def test_admin_profile_experiences_and_education_normalized(client):
    """GET /api/profile for admin must return fully normalized role, company, period, and description."""
    token = create_access_token({"user_id": 1, "email": "pandeytoya22@gmail.com", "role": "admin"})
    resp = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_profile"] is True

    # Experience verification
    experiences = data.get("experience", [])
    assert len(experiences) >= 4
    for exp in experiences:
        assert exp.get("role"), f"Role was empty in experience: {exp}"
        assert exp.get("company"), f"Company was empty in experience: {exp}"
        assert exp.get("period"), f"Period was empty in experience: {exp}"
        assert exp.get("description"), f"Description was empty in experience: {exp}"

    # Education verification
    education = data.get("education", [])
    assert len(education) >= 2
    for edu in education:
        assert edu.get("degree"), f"Degree was empty in education: {edu}"
        assert edu.get("university"), f"University was empty in education: {edu}"
        assert edu.get("graduation_year"), f"Graduation year was empty in education: {edu}"

