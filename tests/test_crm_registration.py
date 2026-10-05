"""Regression tests for dashboard CRM registration.

Covers the bug where a dashboard-generated application was never written to the
CRM: `_save_tracker_df` used to only UPDATE an existing `applications` row, so a
job that had no application row yet was silently dropped.
"""

import sqlite3

from src.dashboard import server


def _make_db(tmp_path, with_application=False):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "karriere.db"
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT NOT NULL, "
        "title TEXT NOT NULL, url TEXT, location TEXT, description TEXT, scraped_at TEXT, "
        "UNIQUE(company, title))"
    )
    c.execute(
        "CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, "
        "cv_pdf_path TEXT, cover_pdf_path TEXT, status TEXT DEFAULT 'Prepared', "
        "applied_at TEXT, notes TEXT, UNIQUE(job_id))"
    )
    c.execute("INSERT INTO jobs (company, title, url) VALUES (?, ?, ?)", ("ACME", "Dev", ""))
    if with_application:
        c.execute(
            "INSERT INTO applications (job_id, cv_pdf_path, cover_pdf_path, status, applied_at, notes) "
            "VALUES (1, 'cv.pdf', 'cl.pdf', 'Interview', '2026-10-05', 'old')"
        )
    conn.commit()
    conn.close()
    return db


def test_register_creates_missing_application_row(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path)

    server._register_application_in_crm(
        "ACME", "Dev", "https://example.com/job/1", "cv_new.pdf", "cl_new.pdf", "ATS notes"
    )

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT cv_pdf_path, cover_pdf_path, status, notes FROM applications WHERE job_id = 1"
    ).fetchone()
    url = conn.execute("SELECT url FROM jobs WHERE id = 1").fetchone()[0]
    conn.close()

    assert row == ("cv_new.pdf", "cl_new.pdf", "Applied", "ATS notes")
    # The new job link must be stored so it resolves in the CRM join.
    assert url == "https://example.com/job/1"


def test_register_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path)

    for _ in range(2):
        server._register_application_in_crm(
            "ACME", "Dev", "https://example.com/job/1", "cv.pdf", "cl.pdf", "n"
        )

    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    conn.close()
    assert count == 1


def test_register_preserves_advanced_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path, with_application=True)

    server._register_application_in_crm(
        "ACME", "Dev", "https://example.com/job/1", "cv_new.pdf", "cl_new.pdf", "new"
    )

    conn = sqlite3.connect(db)
    status = conn.execute("SELECT status FROM applications WHERE job_id = 1").fetchone()[0]
    conn.close()
    # Re-generating must not downgrade a user-set advanced status to 'Applied'.
    assert status == "Interview"


def test_save_tracker_allows_status_change(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path, with_application=True)

    df = server._load_tracker_df()
    df.loc[df["company"] == "ACME", "status"] = "Offer"
    server._save_tracker_df(df)

    conn = sqlite3.connect(db)
    status = conn.execute("SELECT status FROM applications WHERE job_id = 1").fetchone()[0]
    conn.close()
    assert status == "Offer"


def test_explicit_empty_notes_clears_stored_notes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path, with_application=True)

    server._upsert_tracker_row("ACME", "Dev", "https://example.com/job/1", notes="")

    conn = sqlite3.connect(db)
    notes = conn.execute("SELECT notes FROM applications WHERE job_id = 1").fetchone()[0]
    conn.close()
    assert notes == ""


def test_update_by_url_preserves_matched_key_without_duplicate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE jobs SET url = ? WHERE id = 1", ("https://example.com/job/1",))
    conn.commit()
    conn.close()

    # Differing spelling, but the URL identifies the existing job row.
    server._upsert_tracker_row(
        "Acme", "Developer", "https://example.com/job/1", cv_path="cv.pdf", notes="n"
    )

    conn = sqlite3.connect(db)
    jobs = conn.execute("SELECT id, company, title FROM jobs").fetchall()
    app = conn.execute("SELECT job_id, cv_pdf_path FROM applications").fetchone()
    conn.close()
    assert jobs == [(1, "ACME", "Dev")]  # key preserved, no duplicate job
    assert app == (1, "cv.pdf")


def test_single_row_write_never_recreates_a_deleted_application(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO jobs (id, company, title, url) VALUES (2, 'OTHER', 'Role', '')")
    conn.execute("INSERT INTO applications (job_id, status) VALUES (1, 'Applied')")
    conn.execute("INSERT INTO applications (job_id, status) VALUES (2, 'Applied')")
    conn.execute("DELETE FROM applications WHERE job_id = 2")
    conn.commit()
    conn.close()

    server._upsert_tracker_row("ACME", "Dev", "https://example.com/job/1", status="Offer", create=False)

    conn = sqlite3.connect(db)
    other = conn.execute("SELECT COUNT(*) FROM applications WHERE job_id = 2").fetchone()[0]
    conn.close()
    assert other == 0  # a deleted application is not resurrected


def test_register_initializes_database_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    server._register_application_in_crm(
        "ACME", "Dev", "https://example.com/job/1", "cv.pdf", "cl.pdf", "notes"
    )

    db = tmp_path / "data" / "karriere.db"
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT j.company, j.title, a.cv_pdf_path FROM jobs j "
        "JOIN applications a ON a.job_id = j.id"
    ).fetchone()
    conn.close()
    assert row == ("ACME", "Dev", "cv.pdf")


def test_update_by_url_only_when_creation_is_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path, with_application=True)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE jobs SET url = ? WHERE id = 1", ("https://example.com/job/1",))
    conn.commit()
    conn.close()

    updated = server._upsert_tracker_row(
        "", "", "https://example.com/job/1", status="Offer", create=False
    )

    conn = sqlite3.connect(db)
    status = conn.execute("SELECT status FROM applications WHERE job_id = 1").fetchone()[0]
    conn.close()
    assert updated
    assert status == "Offer"


def test_tracker_upsert_begins_immediate_transaction_before_select(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_db(tmp_path, with_application=True)
    statements = []
    original_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", traced_connect)

    server._upsert_tracker_row("ACME", "Dev", status="Offer")

    assert statements[0] == "BEGIN IMMEDIATE"
    assert next(i for i, sql in enumerate(statements) if sql.startswith("SELECT")) > 0
