"""Unit tests for the unified PostgreSQL database layer."""

import os
import unittest.mock as mock
import pytest

from src.db.database import (
    PgConnectionWrapper,
    PgCursorWrapper,
    get_db_connection,
    is_postgres,
)


def test_is_postgres_detection(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert not is_postgres()

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    assert is_postgres()

    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost:5432/db")
    assert is_postgres()

    monkeypatch.setenv("DATABASE_URL", "sqlite:///data/test.db")
    assert not is_postgres()


def test_pg_cursor_translates_placeholders():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    # Placeholders translated
    wrapper.execute("SELECT * FROM jobs WHERE company = ? AND title = ?", ("ACME", "Dev"))
    mock_cur.execute.assert_called_once_with(
        "SELECT * FROM jobs WHERE company = %s AND title = %s",
        ("ACME", "Dev")
    )


def test_pg_cursor_translates_insert_or_ignore():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.execute("INSERT OR IGNORE INTO jobs (company, title) VALUES (?, ?)", ("ACME", "Dev"))
    mock_cur.execute.assert_called_once_with(
        "INSERT INTO jobs (company, title) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        ("ACME", "Dev")
    )


def test_pg_cursor_translates_insert_or_replace_applications():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.execute(
        "INSERT OR REPLACE INTO applications (job_id, cv_pdf_path) VALUES (?, ?)",
        (1, "cv.pdf")
    )
    mock_cur.execute.assert_called_once()
    called_sql = mock_cur.execute.call_args[0][0]
    assert "INSERT INTO applications" in called_sql
    assert "ON CONFLICT (job_id) DO UPDATE SET" in called_sql
    assert "%s" in called_sql


def test_pg_cursor_ignores_begin_immediate():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    res = wrapper.execute("BEGIN IMMEDIATE")
    assert res is None
    mock_cur.execute.assert_not_called()


def test_pg_cursor_translates_datetime_now():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.execute("UPDATE evaluations SET evaluated_at = datetime('now') WHERE job_id = ?", (1,))
    mock_cur.execute.assert_called_once_with(
        "UPDATE evaluations SET evaluated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
        (1,)
    )


def test_pg_cursor_escapes_literal_percent_with_params():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.execute(
        "UPDATE jobs SET url = ? WHERE company = ? AND title = ? AND (url LIKE 'mailto:%')",
        ("https://example.com", "ACME", "Dev")
    )
    mock_cur.execute.assert_called_once_with(
        "UPDATE jobs SET url = %s WHERE company = %s AND title = %s AND (url LIKE 'mailto:%%')",
        ("https://example.com", "ACME", "Dev")
    )


def test_pg_cursor_execute_returns_self():
    mock_cur = mock.MagicMock()
    mock_cur.fetchone.return_value = (42,)
    wrapper = PgCursorWrapper(mock_cur)

    res = wrapper.execute("SELECT 1")
    assert res is wrapper
    assert res.fetchone() == (42,)


def test_pg_connection_context_manager():
    mock_conn = mock.MagicMock()
    wrapper = PgConnectionWrapper(mock_conn)

    with wrapper as conn:
        conn.execute("SELECT 1")

    mock_conn.commit.assert_called_once()


def test_pg_connection_context_manager_rollback_on_error():
    mock_conn = mock.MagicMock()
    wrapper = PgConnectionWrapper(mock_conn)

    with pytest.raises(ValueError):
        with wrapper as conn:
            raise ValueError("Test error")

    mock_conn.rollback.assert_called_once()


def test_merge_databases_postgres_mode(tmp_path, monkeypatch):
    import sqlite3
    from src.db.database import merge_databases

    # Create dummy source SQLite DB
    src_db = str(tmp_path / "source.db")
    s_conn = sqlite3.connect(src_db)
    s_cur = s_conn.cursor()
    s_cur.execute("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            company TEXT,
            title TEXT,
            url TEXT,
            location TEXT,
            description TEXT,
            scraped_at TEXT
        )
    """)
    s_cur.execute("""
        CREATE TABLE evaluations (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            status TEXT,
            score INTEGER,
            chance TEXT,
            archetype TEXT,
            matched_skills TEXT,
            gaps TEXT,
            summary TEXT,
            evaluated_at TEXT
        )
    """)
    s_cur.execute("""
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            cv_pdf_path TEXT,
            cover_pdf_path TEXT,
            applied_at TEXT,
            notes TEXT,
            status TEXT
        )
    """)
    s_cur.execute("""
        INSERT INTO jobs (id, company, title, url, location, description, scraped_at)
        VALUES (1, 'Acme Corp', 'Engineer', 'https://acme.corp/1', 'Remote', 'Extensive job description with more than fifty characters here.', '2026-10-20')
    """)
    s_cur.execute("""
        INSERT INTO evaluations (id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
        VALUES (1, 1, 'APPROVED', 90, 'HIGH', 'backend_platform', 'Python', 'None', 'Great', '2026-10-20')
    """)
    s_cur.execute("""
        INSERT INTO applications (id, job_id, cv_pdf_path, cover_pdf_path, applied_at, notes, status)
        VALUES (1, 1, 'cv.pdf', 'cover.pdf', '2026-10-20', 'notes', 'Applied')
    """)
    s_conn.commit()
    s_conn.close()

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    mock_cur = mock.MagicMock()
    mock_cur.rowcount = 1
    mock_cur.fetchone.return_value = (10,)
    mock_conn = mock.MagicMock()
    mock_conn.cursor.return_value = mock_cur

    with mock.patch("src.db.database.setup_db", return_value=mock_conn):
        stats = merge_databases(src_db)

    assert stats["merged_jobs"] == 1
    assert stats["merged_evaluations"] == 1
    assert stats["merged_applications"] == 1
    assert mock_conn.commit.called
    assert mock_conn.close.called


def test_pg_cursor_executemany_translates_insert_or_ignore():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.executemany(
        "INSERT OR IGNORE INTO jobs (company, title) VALUES (?, ?)",
        [("ACME", "Dev"), ("Beta", "Ops")]
    )
    mock_cur.executemany.assert_called_once()
    called_sql = mock_cur.executemany.call_args[0][0]
    assert "INSERT INTO jobs" in called_sql
    assert "ON CONFLICT DO NOTHING" in called_sql
    assert "%s" in called_sql
    assert "OR IGNORE" not in called_sql


def test_pg_cursor_executemany_escapes_percent():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.executemany(
        "UPDATE jobs SET url = ? WHERE url LIKE 'mailto:%'",
        [("https://example.com/1",), ("https://example.com/2",)]
    )
    mock_cur.executemany.assert_called_once()
    called_sql = mock_cur.executemany.call_args[0][0]
    assert "mailto:%%" in called_sql
    assert "%s" in called_sql


def test_pg_cursor_translates_insert_or_replace_applications_multi_tenant():
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.execute(
        "INSERT OR REPLACE INTO applications (user_id, job_id, cv_pdf_path) VALUES (?, ?, ?)",
        (2, 10, "cv.pdf")
    )
    mock_cur.execute.assert_called_once()
    called_sql = mock_cur.execute.call_args[0][0]
    assert "INSERT INTO applications" in called_sql
    assert "ON CONFLICT (user_id, job_id) DO UPDATE SET" in called_sql
    assert "%s" in called_sql


def test_pg_cursor_lastrowid_with_returning():
    mock_cur = mock.MagicMock()
    mock_cur.description = [("id",)]
    mock_cur.fetchone.return_value = (123,)
    wrapper = PgCursorWrapper(mock_cur)

    wrapper.execute("INSERT INTO scraper_runs (user_id, portal) VALUES (%s, %s) RETURNING id", (1, "indeed"))
    assert wrapper.lastrowid == 123
    assert wrapper.fetchone() == (123,)


def test_pg_connection_wrapper_returns_to_pool():
    mock_conn = mock.MagicMock()
    mock_pool = mock.MagicMock()
    wrapper = PgConnectionWrapper(mock_conn, pool=mock_pool)

    wrapper.close()
    mock_conn.rollback.assert_called_once()
    mock_pool.putconn.assert_called_once_with(mock_conn)
    assert not mock_conn.close.called


def test_pg_connection_wrapper_closes_without_pool():
    mock_conn = mock.MagicMock()
    wrapper = PgConnectionWrapper(mock_conn, pool=None)

    wrapper.close()
    mock_conn.close.assert_called_once()

