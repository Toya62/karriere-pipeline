"""Tests verifying multi-tenant dynamic matching and query generation."""

from src.ai.matcher import build_candidate_matching_prompt
from src.scrapers.query_builder import build_portal_search_queries


def test_matching_prompt_uses_filter_rules_even_for_user_1_when_custom_profile():
    profile = {
        "user_id": 1,
        "archetype": "civil_engineering",
        "filter_rules": {
            "discipline": "Civil Engineering",
            "target_titles": ["Bauingenieur", "Tragwerksplaner"],
            "inclusion_keywords": ["Statik", "AutoCAD", "BIM"],
            "exclusion_keywords": ["Dachdecker", "Software"],
        },
    }
    prompt = build_candidate_matching_prompt(profile, "civil_engineering")
    assert "Bauingenieur" in prompt
    assert "Statik" in prompt
    assert "Python" not in prompt  # Toyanath hardcoded terms must not contaminate
    assert "Strict Negative Exclusions: Dachdecker, Software" in prompt


def test_query_builder_uses_filter_rules_target_titles():
    profile = {
        "user_id": 1,
        "archetype": "civil_engineering",
        "filter_rules": {
            "target_titles": ["Bauingenieur", "Tragwerksplaner"],
        },
    }
    queries = build_portal_search_queries("linkedin", profile)
    assert any("Bauingenieur" in q for q in queries)
    assert not any("PyFlink" in q for q in queries)
