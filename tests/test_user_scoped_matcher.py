"""Unit tests for user-scoped AI matcher."""

import pytest
from unittest.mock import patch, MagicMock
from src.ai.matcher import evaluate_single_job, build_matching_system_prompt


@pytest.fixture
def civil_profile():
    return {
        "user_id": 101,
        "archetype": "civil_engineering",
        "current_title": "Bauingenieur",
        "target_titles": ["Bauingenieur", "Statiker", "Tragwerksplaner"],
        "skills": {
            "core": ["Statik", "Tragwerksplanung", "AutoCAD", "BIM"],
        },
        "languages": {"German": "B2", "English": "C1"},
    }


def test_build_matching_system_prompt_for_civil_engineer(civil_profile):
    prompt = build_matching_system_prompt(civil_profile)
    assert "civil_engineering" in prompt
    assert "Bauingenieur" in prompt
    assert "Statik" in prompt
    # Should not mention Toyanath's CS specifics
    assert "PyFlink" not in prompt


def test_evaluate_single_job_with_civil_profile_approves_civil_job(civil_profile):
    job = {
        "id": 1,
        "title": "Tragwerksplaner (m/w/d)",
        "company": "Ingenieurbüro Statik",
        "location": "Köln",
        "description": "Wir suchen einen Tragwerksplaner / Statiker für anspruchsvolle Hochbau- und Brückenprojekte mit AutoCAD und BIM Kenntnissen. Vollzeit.",
    }

    mock_ai_resp = {
        "fit_score": 88,
        "status": "APPROVED",
        "decision_summary": "Strong match for Civil Engineering & Statik background.",
        "target_archetype": "civil_engineering",
        "recommended_doc_language": "GERMAN",
    }

    with patch("src.ai.matcher.route_ai_evaluation", return_value=mock_ai_resp):
        res = evaluate_single_job(job, candidate_profile=civil_profile)

        assert res is not None
        assert res.get("status") == "APPROVED"
        assert res.get("fit_score") >= 80
        assert res.get("target_archetype") == "civil_engineering"


def test_evaluate_single_job_prefilters_noise_before_ai(civil_profile):
    spam_job = {
        "id": 2,
        "title": "Initiativbewerbung Talents Wanted (m/w/d)",
        "company": "Recruiting GmbH",
        "location": "Berlin",
        "description": "Bewerben Sie sich initiativ bei uns für alle Positionen.",
    }

    with patch("src.ai.matcher.route_ai_evaluation") as mock_ai:
        res = evaluate_single_job(spam_job, candidate_profile=civil_profile)
        # Should be pre-filtered without calling AI API
        assert mock_ai.call_count == 0
        assert res is not None
        assert res.get("status").startswith("REJECTED")


def test_correct_mislabel_does_not_overwrite_tech_mismatch_when_language_ok():
    from src.ai.matcher import _correct_mislabel

    res = {
        "status": "REJECTED_TECH_MISMATCH",
        "decision_summary": "The role requires HL7 and LDT healthcare integration standards not in profile.",
        "language_verdict": {
            "detected_requirement": "German and English",
            "can_apply_with_profiled_level": True,
        },
    }
    corrected = _correct_mislabel(res)
    assert corrected["status"] == "REJECTED_TECH_MISMATCH"


def test_filter_tenant_language_honors_c1_german_candidate():
    import pandas as pd
    from src.core.dynamic_filters import filter_tenant_language

    df = pd.DataFrame([
        {
            "title": "Softwareentwickler (m/w/d)",
            "description": "Wir erwarten verhandlungssicheres Deutsch (C1/C2) in Wort und Schrift.",
        }
    ])
    # B2 candidate is rejected
    b2_out = filter_tenant_language(df, {"countries": ["Germany"]}, german_level="B2")
    assert b2_out.empty

    # C1 candidate is kept
    c1_out = filter_tenant_language(df, {"countries": ["Germany"]}, german_level="C1")
    assert len(c1_out) == 1


def test_build_matching_system_prompt_unified_schema_and_languages():
    from src.ai.matcher import build_matching_system_prompt

    profile = {
        "user_id": 12,
        "archetype": "backend_platform",
        "german_level": "C1",
        "english_level": "B2",
        "skills": {"Languages": ["Python", "SQL"]},
        "target_titles": ["Backend Engineer"],
    }
    prompt = build_matching_system_prompt(profile)
    assert "German (C1)" in prompt
    assert "English (B2)" in prompt
    assert '"match_score"' in prompt
    assert '"tech_stack_overlap"' in prompt
    assert '"language_verdict"' in prompt
