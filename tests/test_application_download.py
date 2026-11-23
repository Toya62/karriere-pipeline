"""Tests for user-scoped application file and ZIP download endpoints."""

import io
import uuid
import zipfile
import pytest
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import get_db_connection, create_user, setup_db, is_postgres


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def test_user_and_headers():
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"downloader_{unique_suffix}@example.com"
    u = create_user(email, "pw", "Downloader User", tier="pro", is_verified=True)
    user_id = u["id"]

    token = create_access_token({"sub": f"user_{user_id}", "user_id": user_id, "id": user_id, "email": email, "role": "candidate"})
    return {"id": user_id, "email": email}, {"Authorization": f"Bearer {token}"}


def test_download_application_single_and_zip(test_client, test_user_and_headers, tmp_path):
    user, headers = test_user_and_headers
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Create dummy job
        test_url = f"https://example.com/job/download-{user['id']}"
        cur.execute("DELETE FROM jobs WHERE url = ?", (test_url,))
        if is_postgres():
            cur.execute(
                "INSERT INTO jobs (title, company, location, url) VALUES ('Software Engineer', 'Siemens AG', 'Munich', ?) RETURNING id",
                (test_url,),
            )
            job_id = cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO jobs (title, company, location, url) VALUES ('Software Engineer', 'Siemens AG', 'Munich', ?)",
                (test_url,),
            )
            job_id = cur.lastrowid

        # Create test files on disk
        app_dir = tmp_path / "applications" / "2026-11-09"
        app_dir.mkdir(parents=True, exist_ok=True)
        cv_file = app_dir / "siemens_cv.pdf"
        cv_file.write_bytes(b"%PDF-1.4 Fake CV Bytes")
        cl_file = app_dir / "siemens_cover.pdf"
        cl_file.write_bytes(b"%PDF-1.4 Fake Cover Letter Bytes")
        meta_file = app_dir / "siemens.meta.json"
        meta_file.write_text('{"company": "Siemens AG", "position": "Software Engineer"}')

        cur.execute(
            "DELETE FROM applications WHERE user_id = ? AND job_id = ?",
            (user["id"], job_id),
        )
        if is_postgres():
            cur.execute(
                """
                INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, status)
                VALUES (?, ?, ?, ?, 'Prepared')
                RETURNING id
                """,
                (user["id"], job_id, str(cv_file), str(cl_file)),
            )
            app_id = cur.fetchone()[0]
        else:
            cur.execute(
                """
                INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, status)
                VALUES (?, ?, ?, ?, 'Prepared')
                """,
                (user["id"], job_id, str(cv_file), str(cl_file)),
            )
            app_id = cur.lastrowid

        conn.commit()
    finally:
        conn.close()

    # 1. Test CV download
    resp_cv = test_client.get(f"/api/applications/{app_id}/download?type=cv", headers=headers)
    assert resp_cv.status_code == 200
    assert resp_cv.headers["content-type"] == "application/pdf"
    assert "attachment" in resp_cv.headers["content-disposition"]
    assert resp_cv.content == b"%PDF-1.4 Fake CV Bytes"

    # 1b. Test CV inline view
    resp_cv_inline = test_client.get(f"/api/applications/{app_id}/download?type=cv&inline=1", headers=headers)
    assert resp_cv_inline.status_code == 200
    assert resp_cv_inline.headers["content-type"] == "application/pdf"
    assert "inline" in resp_cv_inline.headers["content-disposition"]

    # 2. Test Cover Letter download
    resp_cl = test_client.get(f"/api/applications/{app_id}/download?type=cover", headers=headers)
    assert resp_cl.status_code == 200
    assert resp_cl.headers["content-type"] == "application/pdf"
    assert "attachment" in resp_cl.headers["content-disposition"]
    assert resp_cl.content == b"%PDF-1.4 Fake Cover Letter Bytes"

    # 3. Test ZIP bundle download
    resp_zip = test_client.get(f"/api/applications/{app_id}/download?type=zip", headers=headers)
    assert resp_zip.status_code == 200
    assert resp_zip.headers["content-type"] == "application/zip"
    assert "attachment" in resp_zip.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(resp_zip.content))
    names = zf.namelist()
    assert any("cv" in n.lower() for n in names)
    assert any("cover" in n.lower() for n in names)


def test_download_application_access_denied(test_client, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    u1 = create_user(f"owner_{suffix}@example.com", "pw", "Owner", tier="pro", is_verified=True)
    u2 = create_user(f"intruder_{suffix}@example.com", "pw", "Intruder", tier="pro", is_verified=True)
    t2 = create_access_token({"sub": f"user_{u2['id']}", "user_id": u2["id"], "id": u2["id"], "email": u2["email"], "role": "candidate"})

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        test_url = f"https://example.com/job/denied-{suffix}"
        cur.execute("DELETE FROM jobs WHERE url = ?", (test_url,))
        if is_postgres():
            cur.execute("INSERT INTO jobs (title, company, location, url) VALUES ('Dev', 'LockedCorp', 'Berlin', ?) RETURNING id", (test_url,))
            job_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, status) VALUES (?, ?, 'fake_cv.pdf', 'fake_cl.pdf', 'Prepared') RETURNING id",
                (u1["id"], job_id),
            )
            app_id = cur.fetchone()[0]
        else:
            cur.execute("INSERT INTO jobs (title, company, location, url) VALUES ('Dev', 'LockedCorp', 'Berlin', ?)", (test_url,))
            job_id = cur.lastrowid
            cur.execute(
                "INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, status) VALUES (?, ?, 'fake_cv.pdf', 'fake_cl.pdf', 'Prepared')",
                (u1["id"], job_id),
            )
            app_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    resp = test_client.get(f"/api/applications/{app_id}/download?type=zip", headers={"Authorization": f"Bearer {t2}"})
    assert resp.status_code == 403


def test_export_batch_prepared_applications(test_client, test_user_and_headers):
    user, headers = test_user_and_headers
    resp = test_client.get("/api/applications/export-batch?status=prepared", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]


def test_export_dates_endpoint(test_client, test_user_and_headers):
    user, headers = test_user_and_headers
    resp = test_client.get("/api/applications/export-dates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "dates" in data
    assert "latest" in data
    assert "today" in data


def test_export_batch_by_date_and_query_token(test_client, test_user_and_headers):
    user, headers = test_user_and_headers
    token = headers["Authorization"].split(" ")[1]

    # Test downloading via token query param (browser direct link simulation)
    resp = test_client.get(f"/api/applications/export-batch?date=latest&token={token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert len(names) > 0  # Should contain actual application files, never empty!


def test_export_batch_via_cookie(test_client, test_user_and_headers):
    user, headers = test_user_and_headers
    token = headers["Authorization"].split(" ")[1]

    # Simulate browser direct download carrying karriere_auth_token cookie
    test_client.cookies.set("karriere_auth_token", token)
    resp = test_client.get("/api/applications/export-batch?date=latest")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]


def test_export_batch_direct_function_call():
    from src.dashboard.routers.application_download import export_batch
    # Verify no Query object AttributeError when called without params
    res = export_batch(current_user={"id": 1, "role": "admin"})
    assert res.headers["content-type"] == "application/zip"


