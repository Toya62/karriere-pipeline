"""Unit tests for dynamic scraper query builder."""

import pytest
from src.scrapers.query_builder import build_portal_queries


@pytest.fixture
def civil_profile():
    return {
        "user_id": 101,
        "archetype": "civil_engineering",
        "target_titles": ["Bauingenieur", "Tragwerksplaner", "Statiker"],
        "job_search_preferences": {
            "locations": ["Deutschland"],
        },
    }


@pytest.fixture
def data_profile():
    return {
        "user_id": 102,
        "archetype": "data_engineering",
        "target_titles": ["Data Engineer", "Python Developer"],
        "job_search_preferences": {
            "locations": ["Deutschland"],
        },
    }


def test_build_linkedin_queries_for_civil_engineer(civil_profile):
    queries = build_portal_queries(civil_profile, "linkedin")
    assert isinstance(queries, list)
    assert len(queries) > 0
    # Queries should target Bauingenieur / Statiker
    combined = " ".join(queries)
    assert "Bauingenieur" in combined
    assert "Tragwerksplaner" in combined
    assert "Python" not in combined


def test_build_bund_queries_for_civil_engineer(civil_profile):
    queries = build_portal_queries(civil_profile, "bund")
    assert isinstance(queries, list)
    assert "Bauingenieur" in queries
    assert "Statiker" in queries
    # Bund queries are individual terms, not complex booleans
    assert not any(" AND " in q for q in queries)


def test_build_xing_queries_for_data_engineer(data_profile):
    queries = build_portal_queries(data_profile, "xing")
    assert isinstance(queries, list)
    assert "Data Engineer" in queries
    assert "Python Developer" in queries


def test_build_queries_fallback_on_empty_profile():
    queries = build_portal_queries({}, "linkedin")
    assert isinstance(queries, list)
    assert len(queries) > 0
    # Should fall back to default boolean queries
