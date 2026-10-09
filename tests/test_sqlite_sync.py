import os
import sqlite3
import pytest
from src.db import setup_db, DB_PATH


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
    from src.db import save_jobs_to_db

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


def test_dedup_sqlite_only(tmp_path):
    """Verify deduplication filters work purely from SQLite without any CSV files."""
    import pandas as pd
    from src.core.filters import filter_against_existing_catalog, filter_seen_reposts, filter_seen_reposts_by_url

    from datetime import datetime, timezone
    today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    test_db = str(tmp_path / "test_dedup.db")
    conn = setup_db(test_db)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jobs (company, title, url, location, description, scraped_at)
        VALUES ('ExistingCorp', 'Python Engineer', 'https://job.test/1', 'Berlin', 'Great Python Job description.', ?)
    """, (today_str,))
    conn.commit()
    conn.close()

    new_batch = pd.DataFrame([
        {
            'company': 'ExistingCorp',
            'title': 'Python Engineer',
            'job_url': 'https://job.test/1',
            'description': 'Great Python Job description.',
            'date_posted': today_str,
        },
        {
            'company': 'BrandNewCorp',
            'title': 'Rust Engineer',
            'job_url': 'https://job.test/2',
            'description': 'Brand new Rust job description.',
            'date_posted': today_str,
        }
    ])

    # filter_against_existing_catalog should drop job 1 and keep job 2
    filtered = filter_against_existing_catalog(new_batch, catalog_files=[], db_path=test_db)
    assert len(filtered) == 1
    assert filtered.iloc[0]['company'] == 'BrandNewCorp'

    # filter_seen_reposts_by_url using SQLite should drop job 1
    url_filtered = filter_seen_reposts_by_url(new_batch, db_path=test_db)
    assert len(url_filtered) == 1
    assert url_filtered.iloc[0]['company'] == 'BrandNewCorp'

    # filter_seen_reposts (fingerprint + company normalization) using SQLite should drop job 1
    fp_filtered = filter_seen_reposts(new_batch, db_path=test_db)
    assert len(fp_filtered) == 1
    assert fp_filtered.iloc[0]['company'] == 'BrandNewCorp'


def test_filter_known_jobs_fuzzy(tmp_path):
    """Verify filter_known_jobs drops reposts with gender tags or company prefix differences."""
    import pandas as pd
    from src.core.known_jobs import filter_known_jobs

    test_db = str(tmp_path / "test_known.db")
    conn = setup_db(test_db)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jobs (id, company, title, url, location, description, scraped_at)
        VALUES (1, 'Statista', 'Data & Analytics Engineer (m/f/d)', 'https://job.test/old1', 'Berlin', 'desc', '2026-09-28'),
               (2, 'AraCom-Gruppe / AraCom IT Services GmbH', 'Data Engineer (m/w/d)', 'https://job.test/old2', 'Augsburg', 'desc', '2026-09-28'),
               (3, 'LUMASERV', 'System Engineer [gn]', 'https://job.test/old3', 'Koblenz', 'desc', '2026-08-04')
    """)
    cursor.execute("""
        INSERT INTO applications (job_id, cv_pdf_path, status)
        VALUES (1, 'applications/cv1.pdf', 'Applied'),
               (2, 'applications/cv2.pdf', 'Prepared'),
               (3, 'applications/cv3.pdf', 'Applied')
    """)
    conn.commit()
    conn.close()

    new_batch = pd.DataFrame([
        {'company': 'Statista', 'title': 'Analytics Engineer (m/f/d)', 'job_url': 'https://job.test/new1'},
        {'company': 'AraCom IT Services', 'title': 'Data Engineer (m/w/d)', 'job_url': 'https://job.test/new2'},
        {'company': 'LUMASERV', 'title': 'IT System Engineer [gn]', 'job_url': 'https://job.test/new3'},
        {'company': 'FreshStartup GmbH', 'title': 'Python Backend Engineer (m/w/d)', 'job_url': 'https://job.test/fresh'},
    ])

    filtered = filter_known_jobs(new_batch, db_path=test_db)
    assert len(filtered) == 1
    assert filtered.iloc[0]['company'] == 'FreshStartup GmbH'


def test_unknown_url_dismissal_no_collision(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.dashboard.server import _add_to_dismissed
    # Dismiss two different unknown URLs without company/title; should not crash on UNIQUE constraint
    _add_to_dismissed(job_url="https://unknown.portal/job1")
    _add_to_dismissed(job_url="https://unknown.portal/job2")

    conn = sqlite3.connect("data/karriere.db")
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM evaluations WHERE status = 'USER_DISMISSED'")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 2


def test_sync_dismissals_from_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import json
    from src.dashboard.server import sync_dismissals_from_json
    from src.db.database import setup_db

    db_path = "data/karriere.db"
    conn = setup_db(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO jobs (company, title, url) VALUES (?, ?, ?)", ("RemoteCo", "Platform Engineer", "https://remote.test/job"))
    conn.commit()
    conn.close()

    # Simulate pulling crm_dismissals.json from git
    os.makedirs("data", exist_ok=True)
    with open("data/crm_dismissals.json", "w", encoding="utf-8") as f:
        json.dump([
            {"company": "RemoteCo", "position": "Platform Engineer", "job_url": "https://remote.test/job", "dismissed_at": "2026-10-02T10:00:00"}
        ], f)

    # Dismissals are DB-only now; sync_dismissals_from_json is a deprecated no-op
    # that always returns 0. A stale crm_dismissals.json can no longer re-hide jobs.
    synced = sync_dismissals_from_json(db_path)
    assert synced == 0

    # The no-op must NOT have written a USER_DISMISSED evaluation from the JSON file.
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT status FROM evaluations WHERE job_id = (SELECT id FROM jobs WHERE company = 'RemoteCo')")
    row = cur.fetchone()
    conn.close()
    assert row is None  # job was not dismissed by the stale JSON


def test_save_evaluations_validates_job_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.ai.matcher import save_evaluations_to_db
    from src.db.database import setup_db

    db_path = "data/karriere.db"
    conn = setup_db(db_path)
    cur = conn.cursor()
    # Insert job with id=1
    cur.execute("INSERT INTO jobs (id, company, title) VALUES (1, 'RealCompany', 'RealEngineer')")
    conn.commit()
    conn.close()

    # Attempt to save evaluation with forged/mismatched job_id=1 for a different company
    eval_record = {
        "job_id": 1,
        "company": "FakeCompany",
        "title": "FakeEngineer",
        "status": "APPROVED",
        "score": 90,
        "chance": "HIGH",
        "archetype": "Platform",
        "matched_skills": "Python",
        "gaps": "None",
        "summary": "Forged id test"
    }
    save_evaluations_to_db([eval_record], db_path=db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # RealCompany should NOT have this evaluation assigned to it
    cur.execute("SELECT status FROM evaluations WHERE job_id = 1")
    real_eval = cur.fetchone()
    assert real_eval is None

    # FakeCompany should have been inserted with a new distinct ID and evaluated
    cur.execute("SELECT id FROM jobs WHERE company = 'FakeCompany'")
    fake_job = cur.fetchone()
    assert fake_job is not None
    assert fake_job[0] != 1

    cur.execute("SELECT status FROM evaluations WHERE job_id = ?", (fake_job[0],))
    fake_eval = cur.fetchone()
    conn.close()
    assert fake_eval is not None
    assert fake_eval[0] == "APPROVED"



