import sqlite3
import pandas as pd
import pytest
from src.db.database import save_jobs_to_db, setup_db, is_direct_ats_url


def test_is_direct_ats_url():
    assert is_direct_ats_url("https://langdock.jobs.personio.de/job/123") is True
    assert is_direct_ats_url("https://company.jobs.personio.com/job/456") is True
    assert is_direct_ats_url("https://jobs.ashbyhq.com/qdrant/abc-123") is True
    assert is_direct_ats_url("https://boards.greenhouse.io/celonis/jobs/789") is True
    assert is_direct_ats_url("https://startup.recruitee.com/o/developer") is True
    assert is_direct_ats_url("https://bmw.wd3.myworkdayjobs.com/BMWGroupCareers") is True
    assert is_direct_ats_url("https://jobs.lever.co/synthesia/xyz") is True
    assert is_direct_ats_url("https://www.linkedin.com/jobs/view/12345") is False
    assert is_direct_ats_url("https://www.xing.com/jobs/berlin-software-engineer-999") is False
    assert is_direct_ats_url("https://de.indeed.com/viewjob?jk=abcdef") is False


def test_ats_url_upgrades_aggregator_url(tmp_path):
    test_db = tmp_path / "test_dedup.db"
    setup_db(str(test_db))

    # 1. First ingest from LinkedIn (aggregator)
    df_linkedin = pd.DataFrame([{
        "company": "Langdock GmbH",
        "title": "Backend Engineer (m/w/d)",
        "job_url": "https://www.linkedin.com/jobs/view/11223344",
        "location": "Berlin, Germany",
        "description": "Short LinkedIn description.",
        "scraped_at": "2026-11-06 10:00:00"
    }])
    saved_1 = save_jobs_to_db(df_linkedin, db_path=str(test_db))
    assert saved_1 == 1

    # Verify initial row
    conn = sqlite3.connect(str(test_db))
    c = conn.cursor()
    c.execute("SELECT id, company, title, url, description FROM jobs")
    rows = c.fetchall()
    assert len(rows) == 1
    assert rows[0][3] == "https://www.linkedin.com/jobs/view/11223344"
    conn.close()

    # 2. Second ingest from Ashby (direct ATS) for same position
    df_ashby = pd.DataFrame([{
        "company": "Langdock",
        "title": "Backend Engineer",
        "job_url": "https://jobs.ashbyhq.com/langdock/abc-xyz",
        "location": "Berlin, Germany",
        "description": "Comprehensive rich job description directly from Ashby ATS with full technical stack.",
        "scraped_at": "2026-11-07 10:00:00"
    }])
    saved_2 = save_jobs_to_db(df_ashby, db_path=str(test_db))
    # Should update existing record rather than insert a new row
    assert saved_2 == 0

    conn = sqlite3.connect(str(test_db))
    c = conn.cursor()
    c.execute("SELECT id, company, title, url, description FROM jobs")
    rows = c.fetchall()
    assert len(rows) == 1  # ZERO duplicate rows!
    # The URL MUST have been upgraded to the direct ATS apply link
    assert rows[0][3] == "https://jobs.ashbyhq.com/langdock/abc-xyz"
    # Description MUST have been upgraded to the richer version
    assert "Comprehensive rich job description directly from Ashby" in rows[0][4]
    conn.close()


def test_aggregator_url_does_not_overwrite_ats_url(tmp_path):
    test_db = tmp_path / "test_dedup2.db"
    setup_db(str(test_db))

    # 1. First ingest from Personio (direct ATS)
    df_personio = pd.DataFrame([{
        "company": "Qdrant",
        "title": "Senior Rust & Python Engineer",
        "job_url": "https://qdrant.jobs.personio.de/job/98765",
        "location": "Berlin, Germany",
        "description": "Rich Personio description.",
        "scraped_at": "2026-11-06 10:00:00"
    }])
    saved_1 = save_jobs_to_db(df_personio, db_path=str(test_db))
    assert saved_1 == 1

    # 2. Second ingest from LinkedIn (aggregator)
    df_linkedin = pd.DataFrame([{
        "company": "Qdrant Solutions GmbH",
        "title": "Senior Rust & Python Engineer (all genders)",
        "job_url": "https://www.linkedin.com/jobs/view/99887766",
        "location": "Berlin, Germany",
        "description": "Duplicate description.",
        "scraped_at": "2026-11-07 10:00:00"
    }])
    saved_2 = save_jobs_to_db(df_linkedin, db_path=str(test_db))
    assert saved_2 == 0

    conn = sqlite3.connect(str(test_db))
    c = conn.cursor()
    c.execute("SELECT id, url FROM jobs")
    rows = c.fetchall()
    assert len(rows) == 1
    # Personio ATS URL MUST be preserved
    assert rows[0][1] == "https://qdrant.jobs.personio.de/job/98765"
    conn.close()


def test_deduplicate_database_script(tmp_path):
    from scripts.dedup_database import deduplicate_database

    test_db = tmp_path / "test_script_dedup.db"
    conn = setup_db(str(test_db))
    cur = conn.cursor()

    # Insert two duplicates directly into jobs (bypassing save_jobs_to_db)
    cur.execute(
        "INSERT INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)",
        ("Blinkist GmbH", "Senior Data Engineer (m/w/d)", "https://www.linkedin.com/jobs/view/555", "Short")
    )
    job1_id = cur.lastrowid
    cur.execute(
        "INSERT INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)",
        ("Blinkist", "Senior Data Engineer", "https://blinkist.jobs.personio.de/job/777", "Very long comprehensive description from Personio")
    )
    job2_id = cur.lastrowid

    # Add evaluation to job1
    cur.execute("INSERT INTO evaluations (job_id, status, score) VALUES (?, ?, ?)", (job1_id, "APPROVED", 85))
    conn.commit()
    conn.close()

    # Dry-run
    res_dry = deduplicate_database(db_path=str(test_db), dry_run=True)
    assert res_dry["clusters_found"] == 1
    assert res_dry["duplicate_rows"] == 1

    # Apply
    res_apply = deduplicate_database(db_path=str(test_db), dry_run=False)
    assert res_apply["clusters_found"] == 1

    conn = sqlite3.connect(str(test_db))
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, url, description FROM jobs")
    remaining_jobs = cur.fetchall()
    assert len(remaining_jobs) == 1
    # ATS url and rich description won!
    assert remaining_jobs[0][3] == "https://blinkist.jobs.personio.de/job/777"
    assert "Very long comprehensive description" in remaining_jobs[0][4]

    # Evaluation foreign key migrated to surviving job!
    survivor_id = remaining_jobs[0][0]
    cur.execute("SELECT job_id, status, score FROM evaluations")
    evals = cur.fetchall()
    assert len(evals) == 1
    assert evals[0][0] == survivor_id
    assert evals[0][1] == "APPROVED"
    assert evals[0][2] == 85
    conn.close()
