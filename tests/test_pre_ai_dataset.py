"""Tests for the Pre-AI (unmatched/skipped AI) dataset view and match trigger."""

import uuid
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import create_user, get_db_connection, is_postgres


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def test_user_headers():
    suffix = uuid.uuid4().hex[:8]
    email = f"preai_{suffix}@example.com"
    u = create_user(email, "password123", "PreAI User", tier="pro", is_verified=True)
    user_id = u["id"]

    token = create_access_token({
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "id": user_id,
        "email": email,
        "role": "candidate",
    })
    return {"id": user_id, "email": email}, {"Authorization": f"Bearer {token}"}


def test_pre_ai_dataset_view(test_client, test_user_headers):
    user, headers = test_user_headers
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        suffix = uuid.uuid4().hex[:6]
        url_unmatched = f"https://example.com/jobs/unmatched-{suffix}"
        url_matched = f"https://example.com/jobs/matched-{suffix}"

        # Insert 2 jobs scoped to this user
        if is_postgres():
            cur.execute(
                "INSERT INTO jobs (title, company, location, url, scraped_by_user_id) VALUES ('Backend Dev', 'Unmatched Corp', 'Berlin', ?, ?) RETURNING id",
                (url_unmatched, user["id"]),
            )
            job_unmatched_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO jobs (title, company, location, url, scraped_by_user_id) VALUES ('Frontend Dev', 'Matched Corp', 'Munich', ?, ?) RETURNING id",
                (url_matched, user["id"]),
            )
            job_matched_id = cur.fetchone()[0]
            # Match only the second job
            cur.execute(
                "INSERT INTO user_jobs (user_id, job_id, status, score, chance) VALUES (?, ?, 'APPROVED_STRONG', 92, 'HIGH')",
                (user["id"], job_matched_id),
            )
        else:
            cur.execute(
                "INSERT INTO jobs (title, company, location, url, scraped_by_user_id) VALUES ('Backend Dev', 'Unmatched Corp', 'Berlin', ?, ?)",
                (url_unmatched, user["id"]),
            )
            job_unmatched_id = cur.lastrowid
            cur.execute(
                "INSERT INTO jobs (title, company, location, url, scraped_by_user_id) VALUES ('Frontend Dev', 'Matched Corp', 'Munich', ?, ?)",
                (url_matched, user["id"]),
            )
            job_matched_id = cur.lastrowid
            cur.execute(
                "INSERT INTO user_jobs (user_id, job_id, status, score, chance) VALUES (?, ?, 'APPROVED_STRONG', 92, 'HIGH')",
                (user["id"], job_matched_id),
            )
        conn.commit()
    finally:
        conn.close()

    # Query pre_ai dataset
    resp = test_client.get("/api/jobs?dataset=pre_ai", headers=headers)
    assert resp.status_code == 200
    jobs = resp.json()

    urls = [j["job_url"] for j in jobs]
    assert url_unmatched in urls
    assert url_matched not in urls
    matched_item = next(j for j in jobs if j["job_url"] == url_unmatched)
    assert matched_item["gemini_status"] == "UNMATCHED"
    assert matched_item["score"] == 0

