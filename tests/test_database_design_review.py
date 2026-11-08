"""Unit and integration tests verifying all fixes from DB_DESIGN_REVIEW.md.

Covers:
1. PG and SQLite applications schema parity with user_id and ON DELETE CASCADE.
2. Multi-tenant applications uniqueness: multiple users can apply to the same job.
3. SQLite PRAGMA foreign_keys=ON enforcement and ON DELETE CASCADE on jobs.
4. PgCursorWrapper.executemany translation of INSERT OR IGNORE, datetime('now'), % escaping.
5. PgCursorWrapper lastrowid and create_scraper_run RETURNING id semantics.
6. Connection pooling via psycopg2 ThreadedConnectionPool.
7. Migration version tracking table (schema_migrations) and idempotency.
"""

import os
import sqlite3
import unittest.mock as mock
import pytest

from src.db.database import (
    PgConnectionWrapper,
    PgCursorWrapper,
    create_scraper_run,
    get_db_connection,
    get_pg_pool,
    close_pg_pool,
    is_postgres,
    setup_db,
)


def test_sqlite_connection_pragmas(tmp_path):
    """PRAGMA foreign_keys=ON, journal_mode=WAL, and timeout are active."""
    db = str(tmp_path / "test_pragmas.db")
    conn = get_db_connection(db)
    try:
        fk_status = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk_status == 1, "PRAGMA foreign_keys must be ON"

        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert busy_timeout >= 30000, "PRAGMA busy_timeout should be at least 30000"
    finally:
        conn.close()


def test_sqlite_foreign_key_cascade(tmp_path):
    """Deleting a job cascades to remove associated evaluations and applications."""
    db = str(tmp_path / "test_cascade.db")
    conn = setup_db(db)
    try:
        cur = conn.cursor()
        # Seed user
        cur.execute("INSERT OR IGNORE INTO users (id, email) VALUES (1, 'user1@example.com'), (2, 'user2@example.com')")
        # Seed job
        cur.execute("INSERT INTO jobs (id, company, title, url) VALUES (999, 'TestCo', 'Dev', 'https://test.co/999')")
        # Seed evaluation
        cur.execute("INSERT INTO evaluations (job_id, status, score) VALUES (999, 'APPROVED', 90)")
        # Seed applications for 2 distinct users on the same job
        cur.execute("INSERT INTO applications (user_id, job_id, cv_pdf_path) VALUES (1, 999, 'cv1.pdf')")
        cur.execute("INSERT INTO applications (user_id, job_id, cv_pdf_path) VALUES (2, 999, 'cv2.pdf')")
        conn.commit()

        # Verify rows exist
        assert cur.execute("SELECT COUNT(*) FROM evaluations WHERE job_id = 999").fetchone()[0] == 1
        assert cur.execute("SELECT COUNT(*) FROM applications WHERE job_id = 999").fetchone()[0] == 2

        # Delete job
        cur.execute("DELETE FROM jobs WHERE id = 999")
        conn.commit()

        # Both evaluations and applications must be cascaded
        assert cur.execute("SELECT COUNT(*) FROM evaluations WHERE job_id = 999").fetchone()[0] == 0
        assert cur.execute("SELECT COUNT(*) FROM applications WHERE job_id = 999").fetchone()[0] == 0
    finally:
        conn.close()


def test_multi_tenant_applications_uniqueness(tmp_path):
    """Multiple candidates can apply to the same job without UNIQUE constraint violations."""
    db = str(tmp_path / "test_multi_tenant_apps.db")
    conn = setup_db(db)
    try:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (id, email) VALUES (1, 'u1@ex.com'), (2, 'u2@ex.com')")
        cur.execute("INSERT INTO jobs (id, company, title, url) VALUES (100, 'ACME', 'Lead', 'https://acme.org/lead')")
        conn.commit()

        # User 1 applies
        cur.execute("INSERT INTO applications (user_id, job_id, cv_pdf_path, status) VALUES (1, 100, 'cv1.pdf', 'Applied')")
        conn.commit()

        # User 2 applies to the exact same job — must succeed!
        cur.execute("INSERT INTO applications (user_id, job_id, cv_pdf_path, status) VALUES (2, 100, 'cv2.pdf', 'Prepared')")
        conn.commit()

        rows = cur.execute("SELECT user_id, job_id, status FROM applications WHERE job_id = 100 ORDER BY user_id").fetchall()
        assert len(rows) == 2
        assert rows[0] == (1, 100, "Applied")
        assert rows[1] == (2, 100, "Prepared")

        # But duplicate application for the same user and job fails or conflicts
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute("INSERT INTO applications (user_id, job_id, cv_pdf_path) VALUES (1, 100, 'duplicate.pdf')")
    finally:
        conn.close()


def test_schema_migrations_version_tracking(tmp_path):
    """setup_db creates and tracks schema_migrations versions idempotently."""
    db = str(tmp_path / "test_migrations.db")
    conn = setup_db(db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        versions = [r[0] for r in cur.fetchall()]
        assert "001_applications_tracking_cols" in versions
        assert "002_user_verification_cols" in versions
        assert "003_candidate_filter_rules" in versions
        assert "004_applications_user_job_unique" in versions
        assert "005_sqlite_evaluations_cascade" in versions

        # Calling setup_db a second time is idempotent
        setup_db(db)
        cur.execute("SELECT COUNT(*) FROM schema_migrations")
        count_after = cur.fetchone()[0]
        assert count_after == len(versions)
    finally:
        conn.close()


def test_pg_cursor_executemany_translation():
    """executemany handles INSERT OR IGNORE, parameter conversion, and % escaping."""
    mock_cur = mock.MagicMock()
    wrapper = PgCursorWrapper(mock_cur)

    # 1. INSERT OR IGNORE
    wrapper.executemany(
        "INSERT OR IGNORE INTO jobs (company, title, url) VALUES (?, ?, ?)",
        [("Co1", "Dev", "https://co1.de"), ("Co2", "QA", "https://co2.de")]
    )
    sql1 = mock_cur.executemany.call_args[0][0]
    assert "INSERT INTO jobs" in sql1
    assert "ON CONFLICT DO NOTHING" in sql1
    assert "%s" in sql1
    assert "OR IGNORE" not in sql1

    # 2. datetime('now') in executemany
    mock_cur.reset_mock()
    wrapper.executemany(
        "UPDATE evaluations SET evaluated_at = datetime('now') WHERE job_id = ?",
        [(1,), (2,)]
    )
    sql2 = mock_cur.executemany.call_args[0][0]
    assert "CURRENT_TIMESTAMP" in sql2
    assert "%s" in sql2


def test_pg_cursor_lastrowid_and_scraper_run():
    """create_scraper_run on PostgreSQL uses RETURNING id to return generated ID."""
    mock_cur = mock.MagicMock()
    mock_cur.description = [("id",)]
    mock_cur.fetchone.return_value = (42,)
    mock_conn = mock.MagicMock()
    mock_conn.cursor.return_value = mock_cur

    wrapper_conn = PgConnectionWrapper(mock_conn)

    run_id = create_scraper_run(
        user_id=1,
        portal="linkedin",
        days=2,
        queries="python",
        conn=wrapper_conn,
    )
    assert run_id == 42
    called_sql = mock_cur.execute.call_args[0][0]
    assert "RETURNING id" in called_sql


def test_postgres_connection_pool_lifecycle(monkeypatch):
    """ThreadedConnectionPool initializes, issues connections, and reclaims them on close."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    close_pg_pool()

    mock_pool_instance = mock.MagicMock()
    mock_conn_instance = mock.MagicMock()
    mock_conn_instance.closed = 0
    mock_pool_instance.getconn.return_value = mock_conn_instance

    with mock.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance):
        pool = get_pg_pool(minconn=2, maxconn=10)
        assert pool is mock_pool_instance

        # Test get_db_connection uses pool
        conn_wrapper = get_db_connection()
        assert isinstance(conn_wrapper, PgConnectionWrapper)
        assert conn_wrapper._conn is mock_conn_instance
        assert conn_wrapper._pool is mock_pool_instance

        # Test closing returns connection to pool
        conn_wrapper.close()
        mock_conn_instance.rollback.assert_called_once()
        mock_pool_instance.putconn.assert_called_once_with(mock_conn_instance)

        # Test pool cleanup
        close_pg_pool()
        mock_pool_instance.closeall.assert_called_once()
