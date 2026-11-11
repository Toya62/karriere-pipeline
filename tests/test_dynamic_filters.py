"""Unit tests for UserFilterContext and dynamic per-user job filtering."""

import pytest
from src.core.dynamic_filters import UserFilterContext, filter_job_for_user


@pytest.fixture
def civil_engineer_profile():
    return {
        "user_id": 101,
        "archetype": "civil_engineering",
        "current_title": "Bauingenieur",
        "target_titles": ["Bauingenieur", "Tragwerksplaner", "Statiker"],
        "skills": {
            "core": ["Statik", "Tragwerksplanung", "AutoCAD", "BIM"],
        },
        "german_level": "B2",
    }


@pytest.fixture
def data_engineer_profile():
    return {
        "user_id": 102,
        "archetype": "data_engineering",
        "current_title": "Data Engineer",
        "target_titles": ["Data Engineer", "Python Developer"],
        "skills": {
            "core": ["Python", "SQL", "Kafka", "PyFlink"],
        },
        "german_level": "B2",
    }


def test_civil_engineer_passes_civil_jobs_and_rejects_cs_noise(civil_engineer_profile):
    ctx = UserFilterContext.from_profile(civil_engineer_profile)

    civil_job = {
        "title": "Tragwerksplaner / Statiker (m/w/d)",
        "description": "Wir suchen einen Tragwerksplaner mit Kenntnissen in Statik und AutoCAD.",
        "company": "Ingenieurbüro Schmidt",
    }
    approved, reason = filter_job_for_user(civil_job, ctx)
    assert approved is True
    assert reason == ""

    # Should NOT require Python or CS keywords
    assert "python" not in [k.lower() for k in ctx.relevance_keywords]


def test_civil_engineer_does_not_reject_statik_or_bauingenieur_as_noise(civil_engineer_profile):
    ctx = UserFilterContext.from_profile(civil_engineer_profile)
    # Ensure statik and bauingenieur are NOT in noise regex
    assert not ctx.noise_pat.search("Statiker gesucht")
    assert not ctx.noise_pat.search("Bauingenieur Hochbau")


def test_data_engineer_passes_data_jobs_and_rejects_unrelated(data_engineer_profile):
    ctx = UserFilterContext.from_profile(data_engineer_profile)

    data_job = {
        "title": "Junior Data Engineer (Python / SQL)",
        "description": "Entwicklung von ETL-Pipelines mit Kafka und Python.",
        "company": "Tech Corp",
    }
    approved, reason = filter_job_for_user(data_job, ctx)
    assert approved is True

    irrelevant_job = {
        "title": "Zahnarztassistent (m/w/d)",
        "description": "Praxisunterstützung in Berlin.",
        "company": "Zahnarztpraxis",
    }
    approved, reason = filter_job_for_user(irrelevant_job, ctx)
    assert approved is False
    assert "target_title" in reason or "relevance" in reason


def test_universal_spam_rejected_for_all_candidates(civil_engineer_profile, data_engineer_profile):
    civil_ctx = UserFilterContext.from_profile(civil_engineer_profile)
    data_ctx = UserFilterContext.from_profile(data_engineer_profile)

    spam_job = {
        "title": "Initiativbewerbung (m/w/d) - Talents Wanted!",
        "description": "Wir suchen immer Talente für alle Bereiche.",
        "company": "Generic Corp",
    }
    app_civil, reason_civil = filter_job_for_user(spam_job, civil_ctx)
    app_data, reason_data = filter_job_for_user(spam_job, data_ctx)

    assert app_civil is False
    assert "noise" in reason_civil.lower()
    assert app_data is False
    assert "noise" in reason_data.lower()


def test_seniority_rejected_when_candidate_is_junior(civil_engineer_profile):
    ctx = UserFilterContext.from_profile(civil_engineer_profile)

    senior_job = {
        "title": "Head of Construction / Director Bauwesen",
        "description": "Führung von 40 Bauleitern und Budgetverantwortung.",
        "company": "MegaBau AG",
    }
    approved, reason = filter_job_for_user(senior_job, ctx)
    assert approved is False
    assert "seniority" in reason.lower()
