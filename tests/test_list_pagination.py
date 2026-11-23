# tests/test_list_pagination.py
"""Bug #3: server-side pagination on /api/jobs and /api/tracker.

Page 2 returns the next slice and `total` matches the underlying count;
without `limit` both endpoints keep returning the plain full list.
"""
import os
os.environ["DATABASE_URL"] = ""

import uuid

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import (
    create_scraper_run,
    create_user,
    get_db_connection,
    save_jobs_to_db,
    setup_db,
    update_scraper_run,
)

client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_data():
    setup_db()
    uid = uuid.uuid4().hex[:8]
    email = f"page_test_{uid}@example.com"
    user = create_user(
        email=email,
        hashed_password="secret123",
        full_name="Pagination Test User",
        role="candidate",
        tier="pro",
        is_verified=True,
    )
    user_id = user["id"]

    run_id = create_scraper_run(user_id=user_id, portal="indeed", days=1, queries="ml")
    update_scraper_run(run_id=run_id, status="completed", jobs_scraped=3)

    job_rows = [
        {"company": f"Page Co A {uid}", "title": "Dev A", "url": f"https://example.com/page-job-a-{uid}", "location": "Berlin"},
        {"company": f"Page Co B {uid}", "title": "Dev B", "url": f"https://example.com/page-job-b-{uid}", "location": "Munich"},
        {"company": f"Page Co C {uid}", "title": "Dev C", "url": f"https://example.com/page-job-c-{uid}", "location": "Hamburg"},
    ]
    df = pd.DataFrame(job_rows)
    save_jobs_to_db(df, portal="indeed", run_id=run_id, user_id=user_id)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, company FROM jobs WHERE run_id = ?", (run_id,))
    jobs_saved = cur.fetchall()
    # Seed one application per job so /api/tracker has exactly 3 rows.
    for i, (jid, _comp) in enumerate(jobs_saved):
        cur.execute(
            "INSERT INTO applications (user_id, job_id, status, applied_at) VALUES (?, ?, ?, ?)",
            (user_id, jid, "Applied", f"2026-11-0{1 + i}"),
        )
    conn.commit()
    conn.close()

    token = create_access_token(data={
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "id": user_id,
        "email": email,
        "role": "candidate",
    })
    headers = {"Authorization": f"Bearer {token}"}

    return {"user_id": user_id, "run_id": run_id, "headers": headers,
            "urls": [r["url"] for r in job_rows]}


def test_jobs_pages_cover_all_rows_with_matching_total(seeded_data):
    headers = seeded_data["headers"]
    run_id = seeded_data["run_id"]
    p1 = client.get(f"/api/jobs?run_id={run_id}&limit=2&offset=0", headers=headers)
    assert p1.status_code == 200
    body1 = p1.json()
    assert body1["total"] == 3
    assert body1["limit"] == 2
    assert body1["offset"] == 0
    assert len(body1["items"]) == 2

    p2 = client.get(f"/api/jobs?run_id={run_id}&limit=2&offset=2", headers=headers)
    assert p2.status_code == 200
    body2 = p2.json()
    assert body2["total"] == 3
    assert len(body2["items"]) == 1

    urls1 = {j["job_url"] for j in body1["items"]}
    urls2 = {j["job_url"] for j in body2["items"]}
    assert urls1.isdisjoint(urls2)
    assert urls1 | urls2 == set(seeded_data["urls"])


def test_jobs_without_limit_still_returns_full_list(seeded_data):
    res = client.get(f"/api/jobs?run_id={seeded_data['run_id']}", headers=seeded_data["headers"])
    assert res.status_code == 200
    jobs = res.json()
    assert isinstance(jobs, list)
    assert len(jobs) == 3


def test_jobs_offset_beyond_total_returns_empty_page(seeded_data):
    res = client.get(f"/api/jobs?run_id={seeded_data['run_id']}&limit=2&offset=10", headers=seeded_data["headers"])
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    assert body["items"] == []


def test_tracker_pages_cover_all_rows_with_matching_total(seeded_data):
    headers = seeded_data["headers"]
    p1 = client.get("/api/tracker?limit=2&offset=0", headers=headers)
    assert p1.status_code == 200
    body1 = p1.json()
    assert body1["total"] == 3
    assert len(body1["items"]) == 2

    p2 = client.get("/api/tracker?limit=2&offset=2", headers=headers)
    assert p2.status_code == 200
    body2 = p2.json()
    assert body2["total"] == 3
    assert len(body2["items"]) == 1

    urls1 = {r["job_url"] for r in body1["items"]}
    urls2 = {r["job_url"] for r in body2["items"]}
    assert urls1.isdisjoint(urls2)
    assert urls1 | urls2 == set(seeded_data["urls"])


def test_tracker_without_limit_still_returns_full_list(seeded_data):
    res = client.get("/api/tracker", headers=seeded_data["headers"])
    assert res.status_code == 200
    rows = res.json()
    assert isinstance(rows, list)
    assert len(rows) == 3
