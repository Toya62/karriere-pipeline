"""Regression tests for portal routing, BA queries/retries, dedup, filtering, and AI matching."""

import json
from types import ModuleType
import sys
import pandas as pd
import requests

from src.scrapers.routing import normalize_portal_slug
from src.scrapers.query_builder import build_portal_queries
from src.scrapers.greenhouse import parse_greenhouse_job
from src.core.dedup import dedup_job_dataframe
from src.core.dynamic_filters import UserFilterContext, filter_job_for_user
from src.db.database import save_jobs_to_db, setup_db
from src.ai.matcher import (
    MATCHING_SYSTEM_PROMPT,
    _is_admin_cs_profile,
    _sanitize_profile_for_prompt,
    build_matching_system_prompt,
)


def test_normalize_portal_slug_handles_bundesagentur_without_bund_collision():
    assert normalize_portal_slug("Bundesagentur") == "ba"
    assert normalize_portal_slug("Bundesagentur (BA)") == "ba"
    assert normalize_portal_slug("ba") == "ba"
    assert normalize_portal_slug("https://www.arbeitsagentur.de/jobsuche/jobdetail/123") == "ba"
    assert normalize_portal_slug("Bund.de") == "bund"
    assert normalize_portal_slug("interamt") == "bund"
    assert normalize_portal_slug("service.bund") == "bund"


def test_query_builder_bilingual_german_portals_and_non_cs_isolation():
    cs_profile = {
        "user_id": 1,
        "archetype": "systems_engineering",
        "filter_rules": {
            "discipline": "Software, Systems & Data Engineering",
            "target_titles": [
                "Python Developer",
                "Data Engineer",
                "Backend Developer",
                "C++ Developer",
                "Software Engineer",
                "Embedded Software Engineer",
                "DevSecOps Engineer",
                "Cloud Engineer",
            ],
        },
        "job_search_preferences": {
            "countries": ["Germany"],
            "ba_queries": [
                "Python Entwickler",
                "Backend Entwickler",
                "Softwareentwickler Python",
                "C++ Entwickler",
                "Embedded Softwareentwickler",
                "Wissenschaftlicher Mitarbeiter Informatik",
            ],
        },
    }

    ba_queries = build_portal_queries(cs_profile, "Bundesagentur (BA)")
    assert "Python Entwickler" in ba_queries
    assert "Softwareentwickler Python" in ba_queries
    assert "Wissenschaftlicher Mitarbeiter Informatik" in ba_queries
    assert len(ba_queries) > 8

    bund_queries = build_portal_queries(cs_profile, "Bund.de")
    assert "Python Entwickler" in bund_queries or "Softwareentwickler" in bund_queries

    # Non-CS profile must remain isolated even if stale ba_queries existed
    civil_profile = {
        "user_id": 202,
        "archetype": "civil_engineering",
        "filter_rules": {
            "discipline": "Civil Engineering",
            "target_titles": ["Bauingenieur", "Statiker"],
        },
        "job_search_preferences": {
            "countries": ["Germany"],
            "ba_queries": ["Python Entwickler"],
        },
    }
    civil_ba = build_portal_queries(civil_profile, "ba")
    assert civil_ba == ["Bauingenieur", "Statiker"]


def test_ba_scraper_retries_transient_timeouts_and_skips_403_v4_on_empty_200(monkeypatch):
    from src.scrapers import ba

    monkeypatch.setattr(ba.time, "sleep", lambda _: None)
    called_urls = []

    class Resp200Empty:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {}

    def fake_get_empty(url, **kwargs):
        called_urls.append(url)
        assert kwargs.get("verify") is True
        return Resp200Empty()

    monkeypatch.setattr(ba.requests, "get", fake_get_empty)
    assert ba.scrape_arbeitsagentur("NonexistentRole", max_results=5) == []
    assert all("v6/jobs" in u for u in called_urls)

    # Now verify transient timeout retry recovers on second attempt
    attempts = {"n": 0}

    class Resp200Hit:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {
                "stellenangebote": [
                    {
                        "referenznummer": "10000-abc-S",
                        "titel": "Python Entwickler (m/w/d)",
                        "arbeitgeber": "Beispiel GmbH",
                        "arbeitsort": {"ort": "Berlin", "plz": "10115"},
                        "kurzBeschreibung": "Python FastAPI PostgreSQL backend development.",
                    }
                ]
            }

    class Detail200:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {"stellenangebotsBeschreibung": "Python FastAPI Docker SQL backend system engineering."}

    def fake_get_retry(url, **kwargs):
        assert kwargs.get("verify") is True
        if "v6/jobs" in url:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise requests.exceptions.Timeout("connect timeout")
            return Resp200Hit()
        return Detail200()

    monkeypatch.setattr(ba.requests, "get", fake_get_retry)
    rows = ba.scrape_arbeitsagentur("Python", max_results=1)
    assert len(rows) == 1
    assert rows[0]["title"] == "Python Entwickler (m/w/d)"
    assert attempts["n"] == 2


def test_greenhouse_unescapes_html_entities():
    raw_job = {
        "title": "Backend Engineer",
        "location": {"name": "Berlin, Germany"},
        "absolute_url": "https://boards.greenhouse.io/example/jobs/1",
        "content": "&lt;p&gt;Build APIs with &lt;strong&gt;Python&lt;/strong&gt; &amp;amp; Docker.&lt;/p&gt;",
        "updated_at": "2026-11-26T10:00:00Z",
    }
    parsed = parse_greenhouse_job(raw_job, "example")
    assert parsed is not None
    assert "<p>" not in parsed["description"]
    assert "Python" in parsed["description"]
    assert "Docker" in parsed["description"]


def test_dedup_keeps_distinct_companies_with_short_identical_titles_in_same_city(tmp_path):
    test_db = str(tmp_path / "test_distinct_co.db")
    df = pd.DataFrame([
        {
            "company": "Alpha Analytics GmbH",
            "title": "Junior Data Engineer",
            "job_url": "https://alpha.example.com/jobs/1",
            "location": "Berlin, Germany",
            "description": "Python SQL ETL pipelines at Alpha Analytics.",
            "scraped_at": "2026-11-26",
        },
        {
            "company": "Beta Cloud AG",
            "title": "Junior Data Engineer",
            "job_url": "https://beta.example.com/jobs/2",
            "location": "Berlin",
            "description": "Kafka PyFlink data engineering at Beta Cloud.",
            "scraped_at": "2026-11-26",
        },
    ])

    deduped = dedup_job_dataframe(df)
    assert len(deduped) == 2

    saved1 = save_jobs_to_db(df.iloc[[0]], db_path=test_db, portal="linkedin")
    saved2 = save_jobs_to_db(df.iloc[[1]], db_path=test_db, portal="ba")
    assert saved1 == 1
    assert saved2 == 1

    conn = setup_db(test_db)
    cnt = conn.cursor().execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    assert cnt == 2


def test_dynamic_filters_preserves_profile_skills_and_blocks_senior_and_staffing():
    admin_profile = {
        "user_id": 1,
        "archetype": "systems_engineering",
        "personal_info": {"email": "pandeytoya22@gmail.com"},
        "skills": {
            "languages": ["Python", "Java", "C++"],
            "cloud": ["AWS", "Docker", "Kubernetes"],
            "security": ["OWASP", "SIEM", "Wireshark"],
        },
        "filter_rules": {
            "discipline": "Software, Systems & Data Engineering",
            "target_titles": ["Python Developer", "Data Engineer"],
            "inclusion_keywords": ["Python", "Docker"],
            "exclusion_keywords": ["PHP", "SAP"],
            "seniority_level": "Junior/Mid",
            "max_years_experience": 3,
        },
        "job_search_preferences": {"countries": ["Germany"]},
    }
    ctx = UserFilterContext.from_profile(admin_profile, user_id=1)

    for ok_job in [
        {
            "title": "Backend Engineer - Cards",
            "company": "SumUp",
            "location": "Berlin, Germany",
            "description": "Build scalable REST services with Java, Docker, and PostgreSQL.",
        },
        {
            "title": "IT Security Engineer",
            "company": "Workidentity GmbH",
            "location": "Munich, Germany",
            "description": "SIEM monitoring, OWASP security testing, Wireshark traffic inspection.",
        },
        {
            "title": "IT Data Engineering (m/w/d)",
            "company": "Nordzucker AG",
            "location": "Braunschweig, Germany",
            "description": "Data integration and ETL pipelines in AWS cloud.",
        },
        {
            "title": "Founding Engineer",
            "company": "Almedia",
            "location": "Berlin, Germany",
            "description": "Backend systems and AWS automation.",
        },
        {
            "title": "Softwareentwickler (m/w/d)",
            "company": "Rheinmetall",
            "location": "Düsseldorf, Germany",
            "description": "Modern C++ and Embedded Linux systems.",
        },
    ]:
        ok, reason = filter_job_for_user(ok_job, ctx)
        assert ok is True, f"Expected {ok_job['title']} to pass, got {reason}"

    bad_senior = {
        "title": "Senior Python Developer",
        "company": "Acme Tech",
        "location": "Berlin, Germany",
        "description": "Python FastAPI Docker AWS.",
    }
    ok_s, r_s = filter_job_for_user(bad_senior, ctx)
    assert ok_s is False and "seniority" in r_s

    bad_agency = {
        "title": "Python Developer",
        "company": "Jobgether",
        "location": "Berlin, Germany",
        "description": "Python FastAPI Docker.",
    }
    ok_a, r_a = filter_job_for_user(bad_agency, ctx)
    assert ok_a is False and "noise" in r_a

    bad_werkstudent = {
        "title": "Werkstudent Data Engineering (m/w/d)",
        "company": "Acme Tech",
        "location": "Berlin, Germany",
        "description": "Python SQL ETL.",
    }
    ok_w, r_w = filter_job_for_user(bad_werkstudent, ctx)
    assert ok_w is False and "employment_type" in r_w


def test_orchestrator_linkedin_tenant_filtering_enforces_hygiene(monkeypatch):
    import src.scrapers.orchestrator as orch

    captured = []
    li_mod = ModuleType("src.scrapers.linkedin")
    long_desc = (
        "We are building cloud-native Python, SQL, ETL, Apache Kafka, Docker, AWS, "
        "and Linux data engineering systems across distributed backend microservices."
    )
    sample_df = pd.DataFrame([
        {
            "title": "Junior Data Engineer",
            "company": "Real Tech GmbH",
            "location": "Berlin, Germany",
            "job_url": "https://www.linkedin.com/jobs/view/1",
            "description": long_desc,
            "date_posted": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        },
        {
            "title": "Senior Data Engineer",
            "company": "Real Tech GmbH",
            "location": "Berlin, Germany",
            "job_url": "https://www.linkedin.com/jobs/view/2",
            "description": long_desc,
            "date_posted": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        },
        {
            "title": "Python Developer",
            "company": "Ferchau GmbH",
            "location": "Munich, Germany",
            "job_url": "https://www.linkedin.com/jobs/view/3",
            "description": long_desc,
            "date_posted": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        },
        {
            "title": "Werkstudent Backend Python (m/w/d)",
            "company": "Startup GmbH",
            "location": "Hamburg, Germany",
            "job_url": "https://www.linkedin.com/jobs/view/4",
            "description": long_desc,
            "date_posted": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        },
    ])
    li_mod.scrape_linkedin = lambda query, results_wanted=None, hours_old=None, **kwargs: sample_df.copy()
    li_mod.hydrate_linkedin_jobs = lambda df, max_workers=8: df

    monkeypatch.setitem(sys.modules, "src.scrapers.linkedin", li_mod)
    monkeypatch.setattr(orch, "filter_known_jobs", lambda df: df)
    monkeypatch.setattr(orch, "filter_against_existing_catalog", lambda df: df)
    monkeypatch.setattr(orch, "dedup", lambda df: df)
    monkeypatch.setattr(orch.time, "sleep", lambda _: None)
    monkeypatch.setattr(orch, "finalise", lambda df, label, **kwargs: captured.append((label, df)))

    admin_profile = {
        "user_id": 1,
        "archetype": "systems_engineering",
        "filter_rules": {
            "discipline": "Software, Systems & Data Engineering",
            "target_titles": ["Junior Data Engineer", "Python Developer"],
            "inclusion_keywords": ["Python", "SQL", "ETL", "Docker"],
            "seniority_level": "Junior/Mid",
            "max_years_experience": 3,
        },
        "job_search_preferences": {"countries": ["Germany"]},
    }

    orch.run_scrape_linkedin(queries=["Data Engineer"], user_profile=admin_profile)
    assert len(captured) == 1
    label, final_df = captured[0]
    assert label == "LinkedIn"
    assert final_df["title"].tolist() == ["Junior Data Engineer"]


def test_matcher_admin_prompt_and_profile_sanitization():
    admin_db_profile = {
        "archetype": "systems_engineering",
        "personal_info": {"email": "pandeytoya22@gmail.com"},
        "filter_rules": {
            "discipline": "Software, Systems & Data Engineering",
            "target_titles": ["Python Developer", "Data Engineer"],
            "filter_config": {"forbidden_tech_soft": ["azure", "gcp"]},
        },
        "filter_config": {"forbidden_tech_soft": ["azure", "gcp"]},
        "job_search_preferences": {
            "countries": ["Germany"],
            "ba_queries": ["Python Entwickler"],
            "boolean_queries": ['("Python")'],
        },
    }

    assert _is_admin_cs_profile(admin_db_profile, user_id=1) is True
    assert build_matching_system_prompt(admin_db_profile, user_id=1) == MATCHING_SYSTEM_PROMPT

    sanitized = _sanitize_profile_for_prompt(admin_db_profile)
    assert "filter_config" not in sanitized
    assert "filter_config" not in sanitized["filter_rules"]
    assert "ba_queries" not in sanitized["job_search_preferences"]
    assert "boolean_queries" not in sanitized["job_search_preferences"]

    # Non-CS profile even for user_id=1 must never get admin prompt
    civil_override = {
        "user_id": 1,
        "archetype": "civil_engineering",
        "filter_rules": {
            "discipline": "Civil Engineering",
            "target_titles": ["Bauingenieur"],
        },
    }
    assert _is_admin_cs_profile(civil_override, user_id=1) is False
    prompt = build_matching_system_prompt(civil_override, user_id=1)
    assert "Bauingenieur" in prompt
    assert "Toyanath" not in prompt


def test_multi_tenant_saas_user_keeps_react_werkstudent_and_isolated_titles(monkeypatch):
    import src.scrapers.orchestrator as orch

    captured = []
    li_mod = ModuleType("src.scrapers.linkedin")
    desc = (
        "Build responsive web applications with React, TypeScript, Spring Boot, C#, .NET, and REST APIs. "
        "Great mentoring environment for working students and junior software engineers across modern cloud teams. "
    ) * 3
    sample_df = pd.DataFrame([
        {
            "title": "Werkstudent Frontend React Developer (m/w/d)",
            "company": "WebShop GmbH",
            "location": "Berlin, Germany",
            "job_url": "https://www.linkedin.com/jobs/view/9001",
            "description": desc,
            "date_posted": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        },
        {
            "title": "Softwareentwickler C# .NET",
            "company": "Enterprise AG",
            "location": "Munich, Germany",
            "job_url": "https://www.linkedin.com/jobs/view/9002",
            "description": desc,
            "date_posted": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        },
    ])
    li_mod.scrape_linkedin = lambda query, results_wanted=None, hours_old=None, **kwargs: sample_df.copy()
    li_mod.hydrate_linkedin_jobs = lambda df, max_workers=8: df

    monkeypatch.setitem(sys.modules, "src.scrapers.linkedin", li_mod)
    monkeypatch.setattr(orch, "filter_known_jobs", lambda df: df)
    monkeypatch.setattr(orch, "filter_against_existing_catalog", lambda df: df)
    monkeypatch.setattr(orch, "dedup", lambda df: df)
    monkeypatch.setattr(orch.time, "sleep", lambda _: None)
    monkeypatch.setattr(orch, "finalise", lambda df, label, **kwargs: captured.append((label, df)))

    react_student_tenant = {
        "user_id": 42,
        "archetype": "backend_platform",
        "filter_rules": {
            "discipline": "Fullstack Software Engineering",
            "target_titles": ["Werkstudent Frontend React Developer", "Softwareentwickler C# .NET"],
            "inclusion_keywords": ["React", "TypeScript", "C#", ".NET"],
            "seniority_level": "Junior/Mid",
            "max_years_experience": 2,
        },
        "job_search_preferences": {"countries": ["Germany"]},
    }

    orch.run_scrape_linkedin(queries=["React Developer"], user_profile=react_student_tenant)
    assert len(captured) == 1
    assert len(captured[0][1]) == 2

    # Specialized non-admin CS tenant must NOT inherit unrelated _CS_FLEX_TITLES
    data_only_tenant = {
        "user_id": 43,
        "archetype": "data_engineering",
        "filter_rules": {
            "discipline": "Data Engineering",
            "target_titles": ["Data Engineer"],
            "inclusion_keywords": ["Snowflake", "dbt"],
        },
    }
    data_ctx = UserFilterContext.from_profile(data_only_tenant, user_id=43)
    assert "IT Security Engineer" not in data_ctx.target_titles
    assert "Founding Engineer" not in data_ctx.target_titles
    assert "Data Engineer" in data_ctx.target_titles

