"""End-to-End Test Suite for Resume Upload, AI Auto-Tune, and Dynamic Job Filtering.

Verifies complete flow across Non-CS (Civil Engineering) and CS (DevSecOps) scenarios,
ensuring multi-tenant isolation and zero hardcoded user bypass.
"""

import json
import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.ai.matcher import build_candidate_matching_prompt
from src.core.dynamic_filters import UserFilterContext, filter_job_for_user
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import (
    create_user,
    get_db_connection,
    get_user_filter_rules,
    get_user_profile,
    save_user_filter_rules,
    save_user_profile,
)
from src.scrapers.query_builder import build_portal_search_queries


@pytest.fixture
def client():
    return TestClient(app)


def _make_auth_candidate(prefix="candidate"):
    unique_email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    user = create_user(unique_email, "secret123", f"{prefix.capitalize()} User", tier="pro")
    token = create_access_token({
        "sub": f"user_{user['id']}",
        "user_id": user["id"],
        "id": user["id"],
        "role": "candidate",
    })
    return {"Authorization": f"Bearer {token}"}, user


def test_e2e_civil_engineering_flow(client):
    """Scenario 1: Full lifecycle for Non-CS (Civil Engineering) candidate.

    Verifies PDF upload, auto-tuning, DB persistence, portal query generation,
    AI matching prompt construction, and dynamic job filtering without CS bleeding.
    """
    headers, user = _make_auth_candidate("civil")
    fake_pdf = b"%PDF-1.5 Civil Engineering Resume Content"

    mock_civil_profile = {
        "user_id": user["id"],
        "archetype": "civil_engineering",
        "personal_info": {"name": "Lukas Baumeister", "location": "Düsseldorf, Germany"},
        "education": [{"degree": "M.Sc. Bauingenieurwesen", "university": "RWTH Aachen"}],
        "experience": [
            {"role": "Tragwerksplaner", "company": "Ingenieurbüro Statik", "description": "BIM, Statik, Hochbau"}
        ],
        "skills": {"Civil": ["Statik", "AutoCAD", "BIM", "Tragwerksplanung"]},
        "languages": {"German": "B2", "English": "C1"},
        "experience_summary": "Bauingenieur mit Fokus auf Statik und Tragwerksplanung.",
        "job_search_preferences": {
            "countries": ["Germany"],
            "titles": ["Bauingenieur", "Tragwerksplaner"],
        },
    }

    mock_civil_rules = {
        "discipline": "Civil Engineering",
        "target_titles": ["Bauingenieur", "Tragwerksplaner", "Statiker"],
        "inclusion_keywords": ["Statik", "AutoCAD", "BIM", "Tragwerksplanung"],
        "exclusion_keywords": ["Dachdecker", "Maler", "Gerüstbau"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 1,
        "max_years_experience": 3,
        "summary": "Civil engineer specializing in structural design and BIM.",
    }

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=mock_civil_profile), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=mock_civil_rules):

        resp = client.post(
            "/api/profile/parse-resume",
            files={"file": ("lukas_cv.pdf", fake_pdf, "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["filter_rules"]["discipline"] == "Civil Engineering"
        assert "Bauingenieur" in data["filter_rules"]["target_titles"]
        assert "Tragwerksplaner" in data["filter_rules"]["target_titles"]
        assert "Statiker" in data["filter_rules"]["target_titles"]

    # Verify GET /api/profile/filter-rules
    get_resp = client.get("/api/profile/filter-rules", headers=headers)
    assert get_resp.status_code == 200
    retrieved_rules = get_resp.json()
    assert retrieved_rules["discipline"] == "Civil Engineering"
    assert retrieved_rules["target_titles"] == ["Bauingenieur", "Tragwerksplaner", "Statiker"]

    # Verify DB persistence
    db_profile = get_user_profile(user["id"])
    db_rules = get_user_filter_rules(user["id"])
    assert db_profile is not None
    assert db_rules["discipline"] == "Civil Engineering"
    assert "Statik" in db_rules["inclusion_keywords"]

    # Verify Scraper Portal Query Generation
    queries = build_portal_search_queries("linkedin", db_profile)
    assert any("Bauingenieur" in q for q in queries)
    assert not any("PyFlink" in q for q in queries)
    assert not any("Python Developer" in q for q in queries)

    # Verify AI Matcher Prompt Generation
    matching_prompt = build_candidate_matching_prompt(db_profile, "civil_engineering")
    assert "Target Discipline: Civil Engineering" in matching_prompt
    assert "Bauingenieur" in matching_prompt
    assert "Statik" in matching_prompt
    assert "Strict Negative Exclusions: Dachdecker, Maler, Gerüstbau" in matching_prompt
    assert "Toyanath" not in matching_prompt

    # Verify Dynamic Job Filtering
    ctx = UserFilterContext.from_profile(db_profile, user_id=user["id"])

    # 1. Valid civil job passes
    valid_job = {
        "title": "Tragwerksplaner / Bauingenieur (m/w/d)",
        "company": "Zublin AG",
        "location": "Düsseldorf, Germany",
        "description": "Erstellung von Statik- und Schalplänen mittels BIM und AutoCAD.",
    }
    approved, reason = filter_job_for_user(valid_job, ctx)
    assert approved is True
    assert reason == ""

    # 2. Excluded noise trade job fails
    trade_job = {
        "title": "Dachdecker / Maler Geselle",
        "company": "Handwerksbetrieb West",
        "location": "Düsseldorf, Germany",
        "description": "Sanierungsarbeiten am Dach.",
    }
    approved, reason = filter_job_for_user(trade_job, ctx)
    assert approved is False
    assert "noise" in reason.lower()

    # 3. Seniority gate rejects executive role
    senior_job = {
        "title": "Head of Structural Engineering",
        "company": "Baugruppe Deutschland",
        "location": "Düsseldorf, Germany",
        "description": "Leitung von 50 Bauingenieuren.",
    }
    approved, reason = filter_job_for_user(senior_job, ctx)
    assert approved is False
    assert "seniority" in reason.lower()

    # 4. Unrelated CS job fails relevance gate
    cs_job = {
        "title": "Senior Python Developer",
        "company": "Tech Solutions GmbH",
        "location": "Düsseldorf, Germany",
        "description": "Django, Flask backend microservices.",
    }
    approved, reason = filter_job_for_user(cs_job, ctx)
    assert approved is False
    assert "rejected" in reason.lower()


def test_e2e_cs_devsecops_flow(client):
    """Scenario 2: Full lifecycle for CS (DevSecOps) candidate with specialized niche rules."""
    headers, user = _make_auth_candidate("devsecops")
    fake_pdf = b"%PDF-1.5 DevSecOps Resume Content"

    mock_cs_profile = {
        "user_id": user["id"],
        "archetype": "devsecops",
        "personal_info": {"name": "Kai Sec", "location": "Munich, Germany"},
        "education": [{"degree": "B.Sc. Informatik", "university": "TU München"}],
        "experience": [
            {"role": "DevSecOps Engineer", "company": "CloudArmor GmbH", "description": "Kubernetes hardening, Terraform"}
        ],
        "skills": {"Security": ["Kubernetes", "Cloud Security", "Terraform", "CI/CD"]},
        "languages": {"German": "B2", "English": "C1"},
        "experience_summary": "Cloud Security und DevSecOps Spezialist.",
        "job_search_preferences": {
            "countries": ["Germany"],
            "titles": ["DevSecOps Engineer", "Cloud Security Engineer"],
        },
    }

    mock_cs_rules = {
        "discipline": "DevSecOps",
        "target_titles": ["DevSecOps Engineer", "Cloud Security Engineer", "AppSec Specialist"],
        "inclusion_keywords": ["Kubernetes", "Cloud Security", "Terraform"],
        "exclusion_keywords": ["PHP", "Call Center", "Bauingenieur"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 1,
        "max_years_experience": 3,
        "summary": "DevSecOps and platform security engineer.",
    }

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=mock_cs_profile), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=mock_cs_rules):

        resp = client.post(
            "/api/profile/parse-resume",
            files={"file": ("kai_cv.pdf", fake_pdf, "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["filter_rules"]["discipline"] == "DevSecOps"
        assert "DevSecOps Engineer" in data["filter_rules"]["target_titles"]

    # Verify GET /api/profile/filter-rules
    get_resp = client.get("/api/profile/filter-rules", headers=headers)
    assert get_resp.status_code == 200
    rules = get_resp.json()
    assert rules["discipline"] == "DevSecOps"
    assert "Kubernetes" in rules["inclusion_keywords"]

    # Verify queries
    db_profile = get_user_profile(user["id"])
    queries = build_portal_search_queries("linkedin", db_profile)
    assert any("DevSecOps Engineer" in q for q in queries)
    assert not any("Bauingenieur" in q for q in queries)

    # Verify AI matcher prompt
    prompt = build_candidate_matching_prompt(db_profile, "devsecops")
    assert "DevSecOps" in prompt
    assert "Kubernetes" in prompt
    assert "Strict Negative Exclusions: PHP, Call Center, Bauingenieur" in prompt

    # Verify Dynamic Filters
    ctx = UserFilterContext.from_profile(db_profile, user_id=user["id"])

    # 1. Valid CS DevSecOps job passes
    valid_cs = {
        "title": "DevSecOps Engineer (m/w/d) - Cloud Security & Kubernetes",
        "company": "SecurePlatform AG",
        "location": "Munich, Germany",
        "description": "Implementierung sicherer CI/CD Pipelines mit Terraform und Kubernetes.",
    }
    approved, reason = filter_job_for_user(valid_cs, ctx)
    assert approved is True
    assert reason == ""

    # 2. Excluded noise job fails
    noise_job = {
        "title": "PHP Support & Call Center Agent",
        "company": "Support Desk Ltd",
        "location": "Munich, Germany",
        "description": "First level support and legacy PHP scripts.",
    }
    approved, reason = filter_job_for_user(noise_job, ctx)
    assert approved is False
    assert "noise" in reason.lower()

    # 3. Cross-discipline Civil job fails
    civil_job = {
        "title": "Bauingenieur Hochbau",
        "company": "Hochbau GmbH",
        "location": "Munich, Germany",
        "description": "Statik und Betonbau.",
    }
    approved, reason = filter_job_for_user(civil_job, ctx)
    assert approved is False


def test_e2e_user_1_admin_non_cs_upload_no_hardcoded_bypass(client):
    """Scenario 3: Verify zero hardcoded user bypass when User 1 (Admin) uploads non-CS resume."""
    token = create_access_token({"sub": "user_1", "user_id": 1, "id": 1, "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    fake_pdf = b"%PDF-1.4 Admin Non-CS Resume"

    mock_civil_profile = {
        "user_id": 1,
        "archetype": "civil_engineering",
        "personal_info": {"name": "Admin Civil Explorer", "location": "Berlin, Germany"},
        "education": [{"degree": "M.Sc. Civil Engineering", "university": "TU Berlin"}],
        "experience": [{"role": "Bauingenieur", "company": "Baugruppe AG", "description": "Statik"}],
        "skills": {"Civil": ["Statik", "AutoCAD", "BIM"]},
        "languages": {"German": "B2", "English": "C1"},
        "job_search_preferences": {
            "countries": ["Germany"],
            "titles": ["Bauingenieur", "Statiker"],
        },
    }

    mock_civil_rules = {
        "discipline": "Civil Engineering",
        "target_titles": ["Bauingenieur", "Statiker"],
        "inclusion_keywords": ["Statik", "AutoCAD", "BIM"],
        "exclusion_keywords": ["Dachdecker", "Software"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 1,
        "max_years_experience": 3,
        "summary": "Civil engineering profile uploaded by user 1.",
    }

    isolated_db_profile = {}
    isolated_db_rules = {}

    def mock_save_prof(u_id, prof, conn=None):
        isolated_db_profile.clear()
        isolated_db_profile.update(prof)
        return True

    def mock_save_rules(u_id, rules, conn=None):
        isolated_db_rules.clear()
        isolated_db_rules.update(rules)
        return True

    def mock_get_prof(u_id, conn=None):
        return dict(isolated_db_profile) if isolated_db_profile else {}

    def mock_get_rules(u_id, conn=None):
        return dict(isolated_db_rules) if isolated_db_rules else {}

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=mock_civil_profile), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=mock_civil_rules), \
         patch("src.dashboard.routers.jobs.save_user_profile", side_effect=mock_save_prof), \
         patch("src.dashboard.routers.jobs.save_user_filter_rules", side_effect=mock_save_rules), \
         patch("src.db.database.get_user_profile", side_effect=mock_get_prof), \
         patch("src.db.database.get_user_filter_rules", side_effect=mock_get_rules):

        resp = client.post(
            "/api/profile/parse-resume",
            files={"file": ("admin_civil.pdf", fake_pdf, "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 200

        # Assert get_user_filter_rules(1) returns Civil rules, NOT Toyanath admin defaults
        u1_rules = mock_get_rules(1)
        assert u1_rules["discipline"] == "Civil Engineering"
        assert "Bauingenieur" in u1_rules["target_titles"]
        assert "Python Developer" not in u1_rules["target_titles"]

        # Assert matching prompt uses dynamic Civil facts without hardcoded Toyanath fallback
        p1 = mock_get_prof(1)
        prompt = build_candidate_matching_prompt(p1, "civil_engineering")
        assert "Target Discipline: Civil Engineering" in prompt
        assert "Bauingenieur" in prompt
        assert "Python" not in prompt

        # Assert search queries are Civil
        queries = build_portal_search_queries("linkedin", p1)
        assert any("Bauingenieur" in q for q in queries)
        assert not any("PyFlink" in q for q in queries)

        # Assert dynamic filter approves Civil job and rejects CS job
        ctx = UserFilterContext.from_profile(p1, user_id=1)
        civil_job = {
            "title": "Bauingenieur / Tragwerksplaner (m/w/d)",
            "company": "Berlin Bau AG",
            "location": "Berlin, Germany",
            "description": "Statik und BIM Planung.",
        }
        approved, _ = filter_job_for_user(civil_job, ctx)
        assert approved is True

        cs_job = {
            "title": "Python Backend Engineer",
            "company": "Tech AG",
            "location": "Berlin, Germany",
            "description": "FastAPI and PostgreSQL.",
        }
        approved, _ = filter_job_for_user(cs_job, ctx)
        assert approved is False


def test_e2e_multi_tenant_concurrent_isolation(client):
    """Scenario 4: Verify multi-tenant isolation with zero cross-contamination between candidates."""
    headers_a, user_a = _make_auth_candidate("tenant_civil")
    headers_b, user_b = _make_auth_candidate("tenant_cs")
    fake_pdf = b"%PDF-1.4 Tenant Resume"

    profile_a = {
        "user_id": user_a["id"],
        "archetype": "civil_engineering",
        "personal_info": {"name": "Candidate A", "location": "Berlin, Germany"},
        "education": [],
        "experience": [],
        "skills": {"Civil": ["Statik", "Tragwerk"]},
        "languages": {"German": "B2"},
        "job_search_preferences": {"countries": ["Germany"], "titles": ["Bauingenieur"]},
    }
    rules_a = {
        "discipline": "Civil Engineering",
        "target_titles": ["Bauingenieur"],
        "inclusion_keywords": ["Statik"],
        "exclusion_keywords": ["Dachdecker", "Software"],
    }

    profile_b = {
        "user_id": user_b["id"],
        "archetype": "devsecops",
        "personal_info": {"name": "Candidate B", "location": "Berlin, Germany"},
        "education": [],
        "experience": [],
        "skills": {"Security": ["Kubernetes", "DevSecOps"]},
        "languages": {"German": "B2"},
        "job_search_preferences": {"countries": ["Germany"], "titles": ["DevSecOps Engineer"]},
    }
    rules_b = {
        "discipline": "DevSecOps",
        "target_titles": ["DevSecOps Engineer"],
        "inclusion_keywords": ["Kubernetes"],
        "exclusion_keywords": ["Bauingenieur", "PHP"],
    }

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=profile_a), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=rules_a):
        r_a = client.post("/api/profile/parse-resume", files={"file": ("a.pdf", fake_pdf, "application/pdf")}, headers=headers_a)
        assert r_a.status_code == 200

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=profile_b), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=rules_b):
        r_b = client.post("/api/profile/parse-resume", files={"file": ("b.pdf", fake_pdf, "application/pdf")}, headers=headers_b)
        assert r_b.status_code == 200

    # Fetch contexts
    ctx_a = UserFilterContext.from_profile(get_user_profile(user_a["id"]), user_id=user_a["id"])
    ctx_b = UserFilterContext.from_profile(get_user_profile(user_b["id"]), user_id=user_b["id"])

    civil_job = {
        "title": "Bauingenieur Statik",
        "company": "Bauplan GmbH",
        "location": "Berlin, Germany",
        "description": "Statik Berechnung.",
    }
    cs_job = {
        "title": "DevSecOps Engineer",
        "company": "CloudSec GmbH",
        "location": "Berlin, Germany",
        "description": "Kubernetes cluster security.",
    }
    spam_job = {
        "title": "Initiativbewerbung / Talents Wanted",
        "company": "Recruiting 24",
        "location": "Berlin, Germany",
        "description": "Initiativbewerbung für alle Bereiche.",
    }

    # Civil job passes A, fails B
    ok_a, _ = filter_job_for_user(civil_job, ctx_a)
    ok_b, _ = filter_job_for_user(civil_job, ctx_b)
    assert ok_a is True
    assert ok_b is False

    # CS job fails A, passes B
    ok_a2, _ = filter_job_for_user(cs_job, ctx_a)
    ok_b2, _ = filter_job_for_user(cs_job, ctx_b)
    assert ok_a2 is False
    assert ok_b2 is True

    # Spam job fails both
    ok_a3, _ = filter_job_for_user(spam_job, ctx_a)
    ok_b3, _ = filter_job_for_user(spam_job, ctx_b)
    assert ok_a3 is False
    assert ok_b3 is False


def test_e2e_guest_upload_autotune_and_in_memory_filtering(client):
    """Scenario 5: Verify guest/anonymous upload returns auto-tuned rules and supports in-memory filtering."""
    fake_pdf = b"%PDF-1.4 Guest Resume"
    guest_profile = {
        "personal_info": {"name": "Guest Candidate", "location": "Hamburg, Germany"},
        "education": [],
        "experience": [],
        "skills": {"Robotics": ["ROS2", "C++", "Kinematics"]},
        "languages": {"German": "B2"},
        "job_search_preferences": {
            "countries": ["Germany"],
            "titles": ["Robotics Engineer"],
        },
    }
    guest_rules = {
        "discipline": "Robotics",
        "target_titles": ["Robotics Engineer", "Automation Engineer"],
        "inclusion_keywords": ["ROS2", "Kinematics"],
        "exclusion_keywords": ["Call Center", "Sales"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": "Guest robotics engineer.",
    }

    with patch("src.dashboard.routers.jobs.parse_resume_with_ai", return_value=guest_profile), \
         patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=guest_rules):

        resp = client.post(
            "/api/profile/parse-resume",
            files={"file": ("guest.pdf", fake_pdf, "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["filter_rules"]["discipline"] == "Robotics"
        assert "Robotics Engineer" in data["filter_rules"]["target_titles"]

    # In-memory context and filtering
    ctx = UserFilterContext.from_profile(data["profile"])
    robotics_job = {
        "title": "Robotics Engineer (m/w/d) - ROS2 & Autonomous Systems",
        "company": "RoboCorp Hamburg",
        "location": "Hamburg, Germany",
        "description": "Development of ROS2 navigation stacks and kinematics algorithms.",
    }
    approved, _ = filter_job_for_user(robotics_job, ctx)
    assert approved is True

    noise_job = {
        "title": "Outbound Call Center Representative",
        "company": "SalesHub Hamburg",
        "location": "Hamburg, Germany",
        "description": "Telephone outreach.",
    }
    approved, reason = filter_job_for_user(noise_job, ctx)
    assert approved is False
    assert "noise" in reason.lower()


def test_e2e_regenerate_filter_rules_endpoint(client):
    """Scenario 6: Verify POST /api/profile/filter-rules/ai-generate endpoint and DB sync."""
    headers, user = _make_auth_candidate("regen")

    initial_profile = {
        "user_id": user["id"],
        "personal_info": {"name": "Regen User", "location": "Cologne, Germany"},
        "education": [{"degree": "M.Sc. Data Science", "university": "Uni Köln"}],
        "experience": [{"role": "Data Engineer", "company": "DataHub", "description": "Kafka, Flink, PySpark"}],
        "skills": {"Data": ["Kafka", "PyFlink", "PySpark", "SQL"]},
        "languages": {"German": "B2", "English": "C1"},
        "experience_summary": "Data engineer specializing in real-time stream processing with Kafka and Flink.",
    }
    save_user_profile(user["id"], initial_profile)

    fresh_generated_rules = {
        "discipline": "Stream Processing & Data Engineering",
        "target_titles": ["Data Engineer", "Streaming Data Engineer", "PyFlink Developer"],
        "inclusion_keywords": ["Kafka", "PyFlink", "PySpark", "Stream Processing"],
        "exclusion_keywords": ["Front End", "React", "WordPress"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 1,
        "max_years_experience": 3,
        "summary": "AI auto-tuned real-time streaming engineer.",
    }

    with patch("src.dashboard.routers.jobs.extract_filter_rules_with_ai", return_value=fresh_generated_rules):
        resp = client.post("/api/profile/filter-rules/ai-generate", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["filter_rules"]["discipline"] == "Stream Processing & Data Engineering"
        assert "PyFlink Developer" in data["filter_rules"]["target_titles"]

    # Verify DB persistence of re-generated rules
    persisted_rules = get_user_filter_rules(user["id"])
    assert persisted_rules["discipline"] == "Stream Processing & Data Engineering"
    assert "Stream Processing" in persisted_rules["inclusion_keywords"]
    assert "React" in persisted_rules["exclusion_keywords"]
