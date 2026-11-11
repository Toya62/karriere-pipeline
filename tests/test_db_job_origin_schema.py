# tests/test_db_job_origin_schema.py
import pytest
from src.db.database import get_db_connection, setup_db

def test_jobs_table_has_portal_and_origin_columns():
    conn = setup_db()
    cur = conn.cursor()
    cur.execute("SELECT portal, run_id, scraped_by_user_id FROM jobs LIMIT 1;")
    row = cur.fetchone()
    # Query succeeding proves columns exist
    assert True
    conn.close()

def test_user_jobs_table_has_run_id_and_stage():
    conn = setup_db()
    cur = conn.cursor()
    cur.execute("SELECT run_id, pipeline_stage FROM user_jobs LIMIT 1;")
    row = cur.fetchone()
    assert True
    conn.close()
