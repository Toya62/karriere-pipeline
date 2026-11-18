import os
import uuid
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.dashboard.state import CACHE, clear_data_caches
from src.db.database import get_db_connection, is_postgres
from src.dashboard.routers.auth import create_user


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def auth_user():
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"delete_tester_{unique_suffix}@example.com"
    user = create_user(email, "secret123", "Delete Tester", tier="pro", is_verified=True)
    token = create_access_token({
        "sub": f"user_{user['id']}",
        "user_id": user["id"],
        "id": user["id"],
        "email": email,
        "role": "candidate",
    })
    return {"Authorization": f"Bearer {token}"}, user


def test_delete_application_by_id_and_purges_cache(test_client, auth_user, tmp_path):
    headers, user = auth_user
    user_id = user["id"]

    # 1. Create a dummy job and application in DB
    conn = get_db_connection()
    cur = conn.cursor()
    unique_slug = uuid.uuid4().hex[:8]
    cur.execute(
        "INSERT INTO jobs (company, title, url) VALUES (?, ?, ?) RETURNING id" if is_postgres()
        else "INSERT INTO jobs (company, title, url) VALUES (?, ?, ?)",
        (f"Test Delete Co {unique_slug}", f"Senior Delete Dev {unique_slug}", f"https://example.com/delete-job-{unique_slug}"),
    )
    if is_postgres():
        job_id = cur.fetchone()[0]
    else:
        job_id = cur.lastrowid

    # Create dummy files
    apps_dir = os.path.join("applications", "2026-11-18")
    os.makedirs(apps_dir, exist_ok=True)
    cv_file = os.path.join(apps_dir, f"test-del-{job_id}_cv.pdf")
    cov_file = os.path.join(apps_dir, f"test-del-{job_id}_cover.pdf")
    meta_file = os.path.join(apps_dir, f"test-del-{job_id}.meta.json")
    for f in (cv_file, cov_file, meta_file):
        with open(f, "w") as fp:
            fp.write("dummy")

    cur.execute(
        "INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, status) VALUES (?, ?, ?, ?, ?) RETURNING id"
        if is_postgres() else
        "INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, status) VALUES (?, ?, ?, ?, ?)",
        (user_id, job_id, cv_file, cov_file, "Prepared"),
    )
    if is_postgres():
        app_id = cur.fetchone()[0]
    else:
        app_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Seed the cache with a fake entry under tracker_{user_id}
    cache_key = f"tracker_{user_id}"
    CACHE[cache_key] = {"data": [{"id": app_id, "company": "Test Delete Co"}], "time": 9999999999.0}
    assert cache_key in CACHE

    # 2. Call DELETE /api/applications with ID
    resp = test_client.request(
        "DELETE",
        "/api/applications?keep_job=true",
        json={"id": app_id, "cv_pdf_path": cv_file},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Verify user cache was purged
    assert cache_key not in CACHE

    # Verify files were deleted
    assert not os.path.exists(cv_file)
    assert not os.path.exists(cov_file)
    assert not os.path.exists(meta_file)

    # Verify DB row is gone
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM applications WHERE id = ?", (app_id,))
    assert cur.fetchone() is None
    conn.close()


def test_delete_application_batch_ids(test_client, auth_user):
    headers, user = auth_user
    user_id = user["id"]

    conn = get_db_connection()
    cur = conn.cursor()
    ids = []
    for i in range(2):
        cur.execute(
            "INSERT INTO jobs (company, title, url) VALUES (?, ?, ?) RETURNING id" if is_postgres()
            else "INSERT INTO jobs (company, title, url) VALUES (?, ?, ?)",
            (f"Batch Delete Co {i}", f"Role {i}", f"https://example.com/batch-{i}-{uuid.uuid4().hex[:6]}"),
        )
        jid = cur.fetchone()[0] if is_postgres() else cur.lastrowid
        cur.execute(
            "INSERT INTO applications (user_id, job_id, status) VALUES (?, ?, ?) RETURNING id" if is_postgres()
            else "INSERT INTO applications (user_id, job_id, status) VALUES (?, ?, ?)",
            (user_id, jid, "Prepared"),
        )
        aid = cur.fetchone()[0] if is_postgres() else cur.lastrowid
        ids.append(aid)
    conn.commit()
    conn.close()

    # Batch delete
    resp = test_client.request(
        "DELETE",
        "/api/applications?keep_job=true",
        json={"ids": ids},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Verify both deleted from DB
    conn = get_db_connection()
    cur = conn.cursor()
    for aid in ids:
        cur.execute("SELECT id FROM applications WHERE id = ?", (aid,))
        assert cur.fetchone() is None
    conn.close()
