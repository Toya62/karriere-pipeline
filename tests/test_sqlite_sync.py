import os
import sqlite3
import pytest
from src.db import determine_status, setup_db, DB_PATH

def test_determine_status():
    assert determine_status({'status': 'Interview', 'notes': ''}) == 'Interview'
    assert determine_status({'status': 'Prepared', 'notes': '1. Gespräch am 15.10'}) == 'Interview'
    assert determine_status({'status': '', 'notes': 'rejected by email'}) == 'Rejected'
    assert determine_status({'status': 'Applied', 'notes': 'Offer received'}) == 'Offer'
    assert determine_status({'status': '', 'notes': 'ghosted after first round'}) == 'Ghosted'
    assert determine_status({'status': '', 'date_applied': '2026-09-15', 'notes': ''}) == 'Applied'
    assert determine_status({'status': '', 'date_applied': '', 'notes': ''}) == 'Prepared'

def test_sqlite_schema_initialization(tmp_path):
    test_db = tmp_path / "test_karriere.db"
    conn = setup_db(str(test_db))
    cursor = conn.cursor()

    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert 'jobs' in tables
    assert 'evaluations' in tables
    assert 'applications' in tables
    conn.close()


def test_save_jobs_to_db(tmp_path, monkeypatch):
    import pandas as pd
    from src.scraper import save_jobs_to_db

    monkeypatch.chdir(tmp_path)
    test_df = pd.DataFrame([{
        'company': 'Antigravity Test Company',
        'title': 'Senior Python Automation Engineer',
        'job_url': 'https://example.com/test-job',
        'location': 'Berlin, Germany',
        'description': 'Full job description with high detail and requirement specifications.',
        'scraped_at': '2026-10-01 15:00:00'
    }])
    
    saved = save_jobs_to_db(test_df)
    assert saved == 1
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    row = c.execute("SELECT company, title, url, description FROM jobs WHERE company = ?", ('Antigravity Test Company',)).fetchone()
    assert row is not None
    assert row[0] == 'Antigravity Test Company'
    assert row[1] == 'Senior Python Automation Engineer'
    assert row[2] == 'https://example.com/test-job'
    assert 'Full job description' in row[3]
    
    # Cleanup test record
    c.execute("DELETE FROM jobs WHERE company = ?", ('Antigravity Test Company',))
    conn.commit()
    conn.close()


def test_merge_databases(tmp_path):
    from src.db import merge_databases
    
    # 1. Create a dummy source database in tmp_path
    source_db_path = str(tmp_path / "remote_test.db")
    conn_s = sqlite3.connect(source_db_path)
    cur_s = conn_s.cursor()
    cur_s.execute('''
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT UNIQUE,
        title TEXT,
        url TEXT,
        location TEXT,
        description TEXT,
        scraped_at TEXT
    )''')
    cur_s.execute('''
    CREATE TABLE evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        status TEXT,
        score INTEGER,
        chance TEXT,
        archetype TEXT,
        matched_skills TEXT,
        gaps TEXT,
        summary TEXT,
        evaluated_at TEXT
    )''')
    cur_s.execute('''
    CREATE TABLE applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        cv_pdf_path TEXT,
        cover_pdf_path TEXT,
        applied_at TEXT,
        notes TEXT,
        status TEXT
    )''')
    
    cur_s.execute("INSERT INTO jobs (company, title, url, location, description, scraped_at) VALUES (?, ?, ?, ?, ?, ?)",
                  ('Remote Merge Test Corp', 'Lead Systems Architect', 'https://remote.corp/job/1', 'Munich', 'Deep Linux systems experience required.', '2026-10-01'))
    cur_s.execute("INSERT INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (1, 'APPROVED', 92, 'HIGH', 'devsecops', 'Linux, Docker', 'None', 'Top candidate', '2026-10-01'))
    conn_s.commit()
    conn_s.close()
    
    # 2. Merge into DB_PATH
    target_db_path = str(tmp_path / "target.db")
    stats = merge_databases(source_db_path, target_db_path)
    assert stats["merged_jobs"] >= 1
    assert stats["merged_evaluations"] >= 1
    
    # 3. Verify in target DB
    conn_t = sqlite3.connect(target_db_path)
    cur_t = conn_t.cursor()
    row = cur_t.execute("SELECT id, company, title FROM jobs WHERE company = ?", ('Remote Merge Test Corp',)).fetchone()
    assert row is not None
    assert row[1] == 'Remote Merge Test Corp'
    assert row[2] == 'Lead Systems Architect'
    
    job_id = row[0]
    eval_row = cur_t.execute("SELECT score, archetype FROM evaluations WHERE job_id = ?", (job_id,)).fetchone()
    assert eval_row is not None
    assert eval_row[0] == 92
    assert eval_row[1] == 'devsecops'
    
    # 4. Clean up test records
    cur_t.execute("DELETE FROM evaluations WHERE job_id = ?", (job_id,))
    cur_t.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn_t.commit()
    conn_t.close()

