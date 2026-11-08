"""Tests for Binding User Custom Filter Rules to Scrapers and AI Pre-filters."""

import pytest
from src.core.dynamic_filters import UserFilterContext, filter_job_for_user
from src.scrapers.query_builder import build_portal_queries


def test_pipeline_uses_custom_user_filter_rules_over_static_catalogs():
    custom_profile = {
        "user_id": 105,
        "filter_rules": {
            "discipline": "Environmental Engineering",
            "target_titles": ["Umweltingenieur", "Klimaschutzmanager"],
            "inclusion_keywords": ["Klimaschutz", "Treibhausgas", "LCA"],
            "exclusion_keywords": ["Buchhalter", "Software"],
            "seniority_level": "Junior/Mid",
            "min_years_experience": 0,
            "max_years_experience": 3,
        },
    }

    # 1. Bund portal queries
    queries_bund = build_portal_queries(custom_profile, "bund")
    assert "Umweltingenieur" in queries_bund
    assert "Klimaschutzmanager" in queries_bund
    assert "Python Developer" not in queries_bund

    # 2. LinkedIn boolean queries
    queries_li = build_portal_queries(custom_profile, "linkedin")
    assert any("Umweltingenieur" in q for q in queries_li)
    assert not any("PyFlink" in q for q in queries_li)

    # 3. Dynamic Filter Context
    ctx = UserFilterContext.from_profile(custom_profile)
    assert ctx.target_title_pat.search("Senior Umweltingenieur") or ctx.target_title_pat.search("Umweltingenieur (m/w/d)")
    assert ctx.noise_pat.search("Buchhalter gesucht")
    assert not ctx.noise_pat.search("Umweltingenieur gesucht")

    # 4. Job filtering
    job_match = {
        "title": "Umweltingenieur (m/w/d) Nachhaltigkeit",
        "company": "EcoTech Solutions",
        "description": "Erstellung von Ökobilanzen (LCA) und Klimaschutz-Gutachten.",
    }
    approved, reason = filter_job_for_user(job_match, ctx)
    assert approved is True
    assert reason == ""

    job_excluded = {
        "title": "Buchhalter / Finance Specialist (m/w/d)",
        "company": "EcoTech Solutions",
        "description": "Finanzbuchhaltung und Rechnungsprüfung.",
    }
    approved_ex, reason_ex = filter_job_for_user(job_excluded, ctx)
    assert approved_ex is False
    assert "Buchhalter" in reason_ex
