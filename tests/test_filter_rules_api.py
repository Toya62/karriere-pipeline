"""Tests for Candidate Filter Rules CRUD and AI-generate Endpoints."""

import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app

client = TestClient(create_app())


def _create_user_and_token(name: str) -> tuple[int, str]:
    from src.db.database import update_user
    from src.core.security import create_access_token
    email = f"{name.lower()}_{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123!", "full_name": name},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    user_id = data["user"]["id"]
    update_user(user_id, {"is_verified": True})
    token = create_access_token({"user_id": user_id, "email": email, "role": "candidate"})
    return user_id, token


def test_filter_rules_crud_lifecycle():
    _, token = _create_user_and_token("EngineerMax")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Initially returns default/empty rules
    resp = client.get("/api/profile/filter-rules", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "target_titles" in data
    assert "inclusion_keywords" in data
    assert "exclusion_keywords" in data

    # 2. Save custom rules
    new_rules = {
        "discipline": "Civil Engineering",
        "target_titles": ["Bauingenieur", "Statiker"],
        "inclusion_keywords": ["Statik", "AutoCAD", "BIM"],
        "exclusion_keywords": ["Dachdecker", "Maler"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": "Civil engineer specializing in structural design."
    }
    resp = client.post("/api/profile/filter-rules", json=new_rules, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 3. Fetch again and verify saved values
    resp = client.get("/api/profile/filter-rules", headers=headers)
    assert resp.status_code == 200
    saved = resp.json()
    assert saved["discipline"] == "Civil Engineering"
    assert saved["target_titles"] == ["Bauingenieur", "Statiker"]
    assert "Statik" in saved["inclusion_keywords"]
    assert "Dachdecker" in saved["exclusion_keywords"]


def test_filter_rules_tenant_isolation():
    _, token_a = _create_user_and_token("CivilAlice")
    _, token_b = _create_user_and_token("BioBob")

    # Alice sets Civil Engineering rules
    client.post(
        "/api/profile/filter-rules",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "discipline": "Civil Engineering",
            "target_titles": ["Bauingenieur"],
            "inclusion_keywords": ["Statik"],
            "exclusion_keywords": ["Biotechnologie"],
        },
    )

    # Bob sets Biotechnology rules
    client.post(
        "/api/profile/filter-rules",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "discipline": "Biotechnology",
            "target_titles": ["Bioinformatiker"],
            "inclusion_keywords": ["Genomics"],
            "exclusion_keywords": ["Bauingenieur"],
        },
    )

    # Alice must only see Civil Engineering
    resp_a = client.get("/api/profile/filter-rules", headers={"Authorization": f"Bearer {token_a}"})
    assert resp_a.json()["target_titles"] == ["Bauingenieur"]
    assert "Genomics" not in resp_a.json()["inclusion_keywords"]

    # Bob must only see Biotechnology
    resp_b = client.get("/api/profile/filter-rules", headers={"Authorization": f"Bearer {token_b}"})
    assert resp_b.json()["target_titles"] == ["Bioinformatiker"]
    assert "Statik" not in resp_b.json()["inclusion_keywords"]


def test_ai_generate_filter_rules_endpoint():
    _, token = _create_user_and_token("AiCandidate")
    headers = {"Authorization": f"Bearer {token}"}

    # Save a candidate profile first
    client.put(
        "/api/profile",
        headers=headers,
        json={
            "personal_info": {"name": "Test Candidate"},
            "experience_summary": "Chemical engineer with experience in process simulation, Aspen Plus, and fluid dynamics.",
            "skills": {"Tools": ["Aspen Plus", "MATLAB"]},
        },
    )

    mock_ai_rules = {
        "discipline": "Chemical Engineering",
        "target_titles": ["Verfahrensingenieur", "Prozessingenieur"],
        "inclusion_keywords": ["Aspen Plus", "Verfahrenstechnik", "Fluid Dynamics"],
        "exclusion_keywords": ["Web Developer", "Software"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": "Chemical engineer tailored filter rules."
    }

    with patch("src.ai.resume_parser.route_ai_evaluation", return_value=mock_ai_rules):
        resp = client.post("/api/profile/filter-rules/ai-generate", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["filter_rules"]["discipline"] == "Chemical Engineering"
        assert "Verfahrensingenieur" in data["filter_rules"]["target_titles"]

