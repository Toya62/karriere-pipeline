# tests/test_jobs_orthogonal_filters.py
import os
os.environ["DATABASE_URL"] = ""

import pytest
import uuid
import pandas as pd
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import (
    create_user,
    create_scraper_run,
    update_scraper_run,
    save_jobs_to_db,
    get_db_connection,
    setup_db,
)

client = TestClient(app)

@pytest.fixture(scope="module")
def seeded_data():
    os.environ["DATABASE_URL"] = ""
    setup_db()
    uid = uuid.uuid4().hex[:8]
    email = f"filter_test_{uid}@example.com"
    user = create_user(
        email=email,
        hashed_password="hash",
        full_name="Filter Test User",
        role="candidate",
        tier="pro",
        is_verified=True,
    )
    user_id = user["id"]

    run_id = create_scraper_run(user_id=user_id, portal="indeed", days=1, queries="ml")
    update_scraper_run(run_id=run_id, status="completed", jobs_scraped=3)

    co1 = f"Indeed AI Lab {uid}"
    co2 = f"DeepMind Indeed {uid}"
    co3 = f"LinkedIn Corp {uid}"

    # 2 Indeed jobs, 1 LinkedIn job
    job_rows = [
        {"company": co1, "title": "AI Researcher", "url": f"https://example.com/indeed-job-{uuid.uuid4().hex[:6]}", "location": "Remote"},
        {"company": co2, "title": "ML Scientist", "url": f"https://example.com/indeed-job-{uuid.uuid4().hex[:6]}", "location": "London"},
        {"company": co3, "title": "Backend Dev", "url": f"https://example.com/li-job-{uuid.uuid4().hex[:6]}", "location": "Munich"},
    ]
    df = pd.DataFrame(job_rows)
    save_jobs_to_db(df, portal="indeed", run_id=run_id, user_id=user_id)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, company FROM jobs WHERE run_id = ?", (run_id,))
    jobs_saved = cur.fetchall()
    target_job_id = None
    for jid, comp in jobs_saved:
        if comp == co1:
            target_job_id = jid
            break

    # Add evaluation in user_jobs for job 1 (APPROVED, score 90)
    if target_job_id:
        cur.execute(
            """INSERT INTO user_jobs (user_id, job_id, status, score, chance, archetype, pipeline_stage, run_id, evaluated_at)
               VALUES (?, ?, 'APPROVED', 90, 'HIGH', 'backend_platform', 'evaluated', ?, datetime('now'))""",
            (user_id, target_job_id, run_id)
        )
        conn.commit()
    conn.close()

    token = create_access_token({
        "user_id": user_id,
        "email": email,
        "role": "candidate",
        "tier": "pro",
    })
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "user_id": user_id,
        "run_id": run_id,
        "headers": headers,
        "co1": co1,
        "co2": co2,
        "co3": co3,
    }

def test_query_jobs_by_portal_returns_indeed_jobs(seeded_data):
    headers = seeded_data["headers"]
    res = client.get("/api/jobs?portal=indeed", headers=headers)
    assert res.status_code == 200
    jobs = res.json()
    assert isinstance(jobs, list)
    companies = [j["company"] for j in jobs]
    assert seeded_data["co1"] in companies
    assert seeded_data["co2"] in companies

def test_query_jobs_by_run_id_filters_exact_batch(seeded_data):
    headers = seeded_data["headers"]
    run_id = seeded_data["run_id"]
    res = client.get(f"/api/jobs?run_id={run_id}", headers=headers)
    assert res.status_code == 200
    jobs = res.json()
    assert isinstance(jobs, list)
    assert len(jobs) == 3

def test_query_jobs_by_verdict_approved(seeded_data):
    headers = seeded_data["headers"]
    res = client.get("/api/jobs?verdict=approved", headers=headers)
    assert res.status_code == 200
    jobs = res.json()
    assert isinstance(jobs, list)
    assert any(seeded_data["co1"] == j["company"] for j in jobs)

def test_pre_ai_for_user_only_returns_unevaluated(seeded_data):
    headers = seeded_data["headers"]
    res = client.get("/api/jobs?stage=pre_ai", headers=headers)
    assert res.status_code == 200
    jobs = res.json()
    assert isinstance(jobs, list)
    companies = [j["company"] for j in jobs]
    assert seeded_data["co1"] not in companies
    assert seeded_data["co2"] in companies
