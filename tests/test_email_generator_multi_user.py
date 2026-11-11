"""Multi-user and tenant isolation tests for the application email generator."""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.generators.email import generate_application_email, find_matching_applications
from src.generators.application import _build_generation_prompt, _load_template


def test_tenant_user_email_generation_deterministic_fallback():
    tenant_profile = {
        "user_id": 2,
        "personal_info": {
            "name": "Jane Smith",
            "email": "jane.smith@example.org",
            "phone": "+49 170 1234567",
            "location": "Berlin, Germany",
            "linkedin_url": "linkedin.com/in/janesmith",
            "github_url": "github.com/janesmith",
        },
        "experience_summary": "Experienced Cloud and DevOps Engineer with 4 years in AWS.",
    }

    # Force fallback (no Gemini client)
    with patch("src.ai.matcher.get_gemini_client", return_value=None):
        result = generate_application_email(
            company="CloudTech SE",
            position="DevOps Engineer",
            description="We are looking for a DevOps Engineer with Terraform and AWS experience.",
            user_id=2,
            candidate_profile=tenant_profile,
        )

    assert result["success"] is True
    assert result["language"] == "en"
    assert "Jane Smith" in result["subject"]
    assert "Application: DevOps Engineer – Jane Smith" in result["subject"]
    assert "Jane Smith" in result["body"]
    assert "jane.smith@example.org" in result["body"]
    assert "+49 170 1234567" in result["body"]
    assert "Berlin, Germany" in result["body"]
    assert "linkedin.com/in/janesmith" in result["body"]

    # Verify zero leakage of Toyanath Pandey's data
    assert "Toyanath" not in result["body"]
    assert "Toyanath" not in result["subject"]
    assert "Kerckhoff" not in result["body"]
    assert "pandeytoya" not in result["body"]
    assert "Toya62" not in result["body"]


def test_tenant_user_email_german_description():
    tenant_profile = {
        "user_id": 3,
        "personal_info": {
            "name": "Max Mustermann",
            "email": "max@muster.de",
            "phone": "+49 151 9876543",
            "location": "München, Deutschland",
        },
        "experience_summary": "Softwareentwickler mit Schwerpunkt Python und Django.",
    }

    with patch("src.ai.matcher.get_gemini_client", return_value=None):
        result = generate_application_email(
            company="Muster GmbH",
            position="Backend Entwickler",
            description="Wir suchen einen Python Entwickler für unseren Standort in München.",
            user_id=3,
            candidate_profile=tenant_profile,
        )

    assert result["success"] is True
    assert result["language"] == "de"
    assert "Bewerbung als Backend Entwickler – Max Mustermann" in result["subject"]
    assert "Max Mustermann" in result["body"]
    assert "max@muster.de" in result["body"]
    assert "Toyanath" not in result["body"]


def test_tenant_user_email_refuses_when_no_profile_or_name():
    result = generate_application_email(
        company="Tech AG",
        position="Backend Engineer",
        description="Python backend position.",
        user_id=4,
        candidate_profile={},
    )
    assert result["success"] is False
    assert "profile" in result["error"].lower()
    assert "Toyanath" not in result.get("body", "")


def test_find_matching_applications_partitions_by_user_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Create admin PDF
    admin_dir = tmp_path / "applications" / "2026-11-11"
    admin_dir.mkdir(parents=True)
    (admin_dir / "cloudtech-se_devops-engineer_cv.pdf").write_text("admin cv")
    (admin_dir / "cloudtech-se_devops-engineer_cover.pdf").write_text("admin cover")

    # Create tenant user_2 PDF
    tenant_dir = tmp_path / "applications" / "user_2" / "2026-11-11"
    tenant_dir.mkdir(parents=True)
    (tenant_dir / "cloudtech-se_devops-engineer_cv.pdf").write_text("tenant cv")
    (tenant_dir / "cloudtech-se_devops-engineer_cover.pdf").write_text("tenant cover")

    # Admin lookup
    admin_matched = find_matching_applications("CloudTech SE", "DevOps Engineer", user_id=1)
    assert len(admin_matched) == 2
    assert "user_2" not in admin_matched[0]["path"]

    # Tenant lookup
    tenant_matched = find_matching_applications("CloudTech SE", "DevOps Engineer", user_id=2)
    assert len(tenant_matched) == 2
    assert "user_2" in tenant_matched[0]["path"]


def test_english_cv_generation_prompt_mandates_english_headers():
    prompt = _build_generation_prompt(
        company="Global Tech",
        position="Platform Engineer",
        description="Build scalable cloud infrastructure with Kubernetes and Python.",
        cv_template="\\section{Profil}\nDefault profile.",
        cl_template="Cover letter template.",
        language="en",
        agents_rules="AGENTS_RULES",
        candidate_profile="CANDIDATE_PROFILE",
        user_id=2,
    )
    assert "DOCUMENT LANGUAGE: ENGLISH" in prompt
    assert "\\section{Professional Summary}" in prompt
    assert "\\section{Work Experience}" in prompt
    assert "\\section{Selected Projects}" in prompt
    assert "\\section{Education}" in prompt
    assert "\\section{Technical Skills \\& Languages}" in prompt
    assert "ABSOLUTELY NO German words" in prompt


def test_load_template_translates_german_boilerplate_for_english():
    template_content = r"\section{Profil} Summary \section{Berufserfahrung} Work \section{Ausbildung} Edu"
    with patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=lambda f: MagicMock(read=lambda: template_content)))):
        with patch("os.path.exists", return_value=True):
            rendered = _load_template(
                filename="cv_template_backend.tex",
                candidate_dict={
                    "personal_info": {"name": "Alice Developer", "email": "alice@dev.com"}
                },
                user_id=2,
                language="en",
            )
            assert r"\section{Professional Summary}" in rendered
            assert r"\section{Work Experience}" in rendered
            assert r"\section{Education}" in rendered
            assert r"\section{Profil}" not in rendered
            assert r"\section{Berufserfahrung}" not in rendered

