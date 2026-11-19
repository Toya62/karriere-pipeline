"""tests/test_database_dedup.py — Tests for database 5-tier deduplication and dashboard deduplication."""

import os
import sqlite3
import tempfile
import pandas as pd
import pytest

from src.db.database import setup_db, dedup_database
from src.dashboard.routers.jobs import clean_jobs_df


@pytest.fixture
def temp_test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = setup_db(path)
    conn.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_dedup_database_merges_cross_portal_duplicates(temp_test_db):
    conn = sqlite3.connect(temp_test_db)
    c = conn.cursor()

    # Insert two jobs from different portals representing the same role
    c.execute("""
    INSERT INTO jobs (id, company, title, url, location, description, portal)
    VALUES (1, 'Acme Corp', 'Senior Backend Engineer (m/w/d)', 'https://www.xing.com/jobs/123', 'Berlin', 'Short snippet', 'xing')
    """)
    c.execute("""
    INSERT INTO jobs (id, company, title, url, location, description, portal)
    VALUES (2, 'Acme Corp GmbH', 'Senior Backend Developer', 'https://jobs.lever.co/acme/456', 'Berlin', 'Comprehensive full job description with rich requirements and benefits text.', 'lever')
    """)

    # Job 1 has lower score evaluation, Job 2 has higher score
    c.execute("""
    INSERT INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
    VALUES (1, 'APPROVED_GERMAN_B2', 80, 'MEDIUM', 'backend_platform', 'Python', 'Go', 'Good match', '2026-11-19')
    """)
    c.execute("""
    INSERT INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
    VALUES (2, 'APPROVED_ENGLISH', 92, 'HIGH', 'backend_platform', 'Python, Docker, AWS', 'None', 'Great match', '2026-11-19')
    """)

    # Job 2 has an application prepared
    c.execute("""
    INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, status, applied_at, notes)
    VALUES (1, 2, 'applications/2026-11-19/acme_cv.pdf', 'applications/2026-11-19/acme_cover.pdf', 'Prepared', '2026-11-19', 'Ready to send')
    """)

    # User 1 also has user_jobs for both
    c.execute("""
    INSERT INTO user_jobs (user_id, job_id, status, score, chance, archetype)
    VALUES (1, 1, 'APPROVED_GERMAN_B2', 80, 'MEDIUM', 'backend_platform')
    """)
    c.execute("""
    INSERT INTO user_jobs (user_id, job_id, status, score, chance, archetype, is_bookmarked)
    VALUES (1, 2, 'APPROVED_ENGLISH', 92, 'HIGH', 'backend_platform', 1)
    """)

    conn.commit()
    conn.close()

    # Run database deduplication
    stats = dedup_database(temp_test_db)
    assert stats["examined"] == 2
    assert stats["merged"] == 1
    assert stats["remaining"] == 1

    conn = sqlite3.connect(temp_test_db)
    c = conn.cursor()

    # Verify only 1 job remains
    c.execute("SELECT id, company, title, url, description, portal FROM jobs")
    jobs = c.fetchall()
    assert len(jobs) == 1
    remaining_job = jobs[0]
    rem_id, rem_comp, rem_title, rem_url, rem_desc, rem_portal = remaining_job

    # Canonical job should have direct ATS URL promoted
    assert "jobs.lever.co" in rem_url
    # Rich description retained
    assert "Comprehensive full job description" in rem_desc
    # Portals combined
    assert "lever" in rem_portal and "xing" in rem_portal

    # Verify evaluation preserved with highest score (92)
    c.execute("SELECT job_id, score, status FROM evaluations")
    evals = c.fetchall()
    assert len(evals) == 1
    assert evals[0][0] == rem_id
    assert evals[0][1] == 92

    # Verify application repointed to remaining job
    c.execute("SELECT job_id, cv_pdf_path, status FROM applications")
    apps = c.fetchall()
    assert len(apps) == 1
    assert apps[0][0] == rem_id
    assert apps[0][1] == "applications/2026-11-19/acme_cv.pdf"

    # Verify user_jobs repointed and bookmarked
    c.execute("SELECT job_id, score, is_bookmarked FROM user_jobs")
    u_jobs = c.fetchall()
    assert len(u_jobs) == 1
    assert u_jobs[0][0] == rem_id
    assert u_jobs[0][1] == 92
    assert u_jobs[0][2] == 1

    # Verify zero foreign key violations
    c.execute("PRAGMA foreign_key_check")
    assert c.fetchall() == []
    conn.close()


def test_clean_jobs_df_deduplicates_cross_portal_and_combines_tags():
    raw_jobs = [
        {
            "company": "dotSource SE",
            "title": "Cloud Engineer (m/w/d)",
            "job_url": "https://www.xing.com/jobs/158246444",
            "location": "Jena",
            "portal": "xing",
            "score": 88,
            "description": "Short summary",
        },
        {
            "company": "dotSource SE",
            "title": "Cloud-Entwickler",
            "job_url": "https://www.linkedin.com/jobs/view/4462145929",
            "location": "Jena",
            "portal": "linkedin",
            "score": 88,
            "description": "Full rich description with comprehensive tech stack requirements and benefits.",
        },
        {
            "company": "Siemens AG",
            "title": "Software Developer (m/w/d)",
            "job_url": "https://de.indeed.com/viewjob?jk=12345",
            "location": "München",
            "portal": "indeed",
            "score": 90,
            "description": "Siemens role",
        },
    ]

    df = pd.DataFrame(raw_jobs)
    cleaned = clean_jobs_df(df)

    # 3 raw rows -> 2 unique jobs
    assert len(cleaned) == 2

    # dotSource row must have combined portals
    ds_row = cleaned[cleaned["company"].str.contains("dotSource")].iloc[0]
    assert "linkedin" in ds_row["portal"]
    assert "xing" in ds_row["portal"]
    # Longest description preserved
    assert "Full rich description" in ds_row["description"]
