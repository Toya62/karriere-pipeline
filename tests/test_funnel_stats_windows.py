# tests/test_funnel_stats_windows.py
"""Bug #2: Overview numbers — windowed counts can never exceed all-time counts.

The funnel-stats endpoint now returns every windowed count together with its
all-time twin, computed from the same snapshot in a single response, plus a
`computed_at` timestamp. These tests seed a fixed mix of recent and old rows
and assert exact values for both windows on the candidate path (user-scoped),
and a strict windowed < all-time inequality on the admin path (the admin
count is global, so exact values cannot be asserted in a shared test DB).
"""
import os

os.environ["DATABASE_URL"] = ""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_scraper_run, create_user, get_db_connection, setup_db

client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_data():
    setup_db()
    uid = uuid.uuid4().hex[:8]
    today = date.today()
    recent = (today - timedelta(days=5)).isoformat()
    old = (today - timedelta(days=60)).isoformat()

    user = create_user(
        email=f"funnel_test_{uid}@example.com",
        hashed_password="x" * 10,
        full_name="Funnel Stats Test User",
        role="candidate",
        tier="pro",
        is_verified=True,
    )
    user_id = user["id"]
    admin = create_user(
        email=f"funnel_admin_{uid}@example.com",
        hashed_password="x" * 10,
        full_name="Funnel Stats Admin",
        role="admin",
        tier="pro",
        is_verified=True,
    )
    admin_id = admin["id"]

    run_id = create_scraper_run(user_id=user_id, portal="indeed", days=1, queries="ml")

    conn = get_db_connection()
    cur = conn.cursor()
    # 10 jobs: 6 scraped 5 days ago (inside the 30-day window), 4 scraped
    # 60 days ago (outside it). Date-only strings: the window filters compare
    # scraped_at lexicographically against YYYY-MM-DD bounds.
    job_ids = []
    for i in range(10):
        scraped_at = recent if i < 6 else old
        cur.execute(
            "INSERT INTO jobs (company, title, url, location, description, portal, scraped_at, run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"Funnel Co {i} {uid}",
                f"Dev {i}",
                f"https://example.com/funnel-job-{i}-{uid}",
                "Berlin",
                "desc",
                "indeed",
                scraped_at,
                run_id,
            ),
        )
        job_ids.append(cur.lastrowid)
    # Candidate evaluated 8 of the 10 jobs: 5 recent (2 APPROVED, 3 EVALUATED),
    # 3 old (1 APPROVED, 2 EVALUATED). The 2 remaining recent jobs are
    # unevaluated, so they never appear in the candidate counts.
    eval_rows = [
        (0, "APPROVED", (today - timedelta(days=2)).isoformat()),
        (1, "APPROVED", (today - timedelta(days=2)).isoformat()),
        (2, "EVALUATED", (today - timedelta(days=2)).isoformat()),
        (3, "EVALUATED", (today - timedelta(days=2)).isoformat()),
        (4, "EVALUATED", (today - timedelta(days=2)).isoformat()),
        (6, "APPROVED", old),
        (7, "EVALUATED", old),
        (8, "EVALUATED", old),
    ]
    for job_idx, status, evaluated_at in eval_rows:
        cur.execute(
            "INSERT INTO user_jobs (user_id, job_id, status, evaluated_at) VALUES (?, ?, ?, ?)",
            (user_id, job_ids[job_idx], status, evaluated_at),
        )
    # 3 applications: 2 applied 3 days ago, 1 applied 60 days ago.
    for job_idx, applied_at in [
        (0, (today - timedelta(days=3)).isoformat()),
        (1, (today - timedelta(days=3)).isoformat()),
        (6, old),
    ]:
        cur.execute(
            "INSERT INTO applications (user_id, job_id, status, applied_at) VALUES (?, ?, ?, ?)",
            (user_id, job_ids[job_idx], "Applied", applied_at),
        )
    conn.commit()
    conn.close()

    candidate_token = create_access_token(data={"sub": f"user_{user_id}", "user_id": user_id})
    admin_token = create_access_token(data={"sub": f"user_{admin_id}", "user_id": admin_id})
    return {"candidate": candidate_token, "admin": admin_token}


def test_candidate_30d_and_all_time_counts(seeded_data):
    """Bug #2: 30-day counts are exact, all-time counts are exact, 30d <= all-time."""
    headers = {"Authorization": f"Bearer {seeded_data['candidate']}"}
    r = client.get("/api/funnel-stats?days=30", headers=headers)
    assert r.status_code == 200
    body = r.json()
    counts = body["counts"]

    assert body.get("computed_at"), "computed_at timestamp missing from funnel-stats"
    # Windowed (30d) counts — only the recent rows.
    assert counts["total_jobs"] == 5
    assert counts["total_evaluated"] == 5
    assert counts["total_approved"] == 2
    assert counts["total_applied"] == 2
    # All-time twins from the same snapshot — the full seeded set.
    assert counts["total_jobs_all_time"] == 8
    assert counts["total_evaluated_all_time"] == 8
    assert counts["total_approved_all_time"] == 3
    assert counts["total_applied_all_time"] == 3
    # The reported symptom (30d > all-time) is impossible in one response.
    assert counts["total_jobs"] <= counts["total_jobs_all_time"]
    assert counts["total_evaluated"] <= counts["total_evaluated_all_time"]
    assert counts["total_approved"] <= counts["total_approved_all_time"]
    assert counts["total_applied"] <= counts["total_applied_all_time"]


def test_candidate_all_time_call_window_equals_all_time(seeded_data):
    """Bug #2: with no window, windowed and all-time counts coincide."""
    headers = {"Authorization": f"Bearer {seeded_data['candidate']}"}
    r = client.get("/api/funnel-stats", headers=headers)
    assert r.status_code == 200
    counts = r.json()["counts"]
    assert counts["total_jobs"] == counts["total_jobs_all_time"] == 8
    assert counts["total_evaluated"] == counts["total_evaluated_all_time"] == 8
    assert counts["total_approved"] == counts["total_approved_all_time"] == 3
    assert counts["total_applied"] == counts["total_applied_all_time"] == 3


def test_admin_30d_below_all_time(seeded_data):
    """Bug #2: admin counts all jobs globally; the 4 old seeded jobs keep
    the 30-day figure strictly below the all-time figure in one response."""
    headers = {"Authorization": f"Bearer {seeded_data['admin']}"}
    r = client.get("/api/funnel-stats?days=30", headers=headers)
    assert r.status_code == 200
    body = r.json()
    counts = body["counts"]
    assert body.get("computed_at"), "computed_at timestamp missing from funnel-stats"
    assert counts["total_jobs"] < counts["total_jobs_all_time"]
    assert counts["total_jobs_all_time"] >= 10
