"""Unit tests for credential documents management (/api/documents)."""

import base64
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app

client = TestClient(create_app())


def test_list_documents():
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert "documents" in data
    keys = [d["key"] for d in data["documents"]]
    assert "degree_certificate" in keys
    assert "job_references" in keys
    assert "transcripts" in keys
    assert "certifications" in keys


def test_upload_invalid_category():
    from src.core.security import create_access_token
    token = create_access_token({"user_id": 1, "email": "pandeytoya22@gmail.com"})
    headers = {"Authorization": f"Bearer {token}"}

    dummy_b64 = base64.b64encode(b"%PDF-1.4 dummy content").decode()
    resp = client.post(
        "/api/documents/upload",
        headers=headers,
        json={"category": "invalid_cat", "file_base64": dummy_b64},
    )
    assert resp.status_code == 400
    msg = resp.json().get("error") or resp.json().get("detail")
    assert "Invalid category" in msg


def test_upload_non_pdf():
    from src.core.security import create_access_token
    token = create_access_token({"user_id": 1, "email": "pandeytoya22@gmail.com"})
    headers = {"Authorization": f"Bearer {token}"}

    dummy_b64 = base64.b64encode(b"not a pdf stream").decode()
    resp = client.post(
        "/api/documents/upload",
        headers=headers,
        json={"category": "master_urkunde", "file_base64": dummy_b64},
    )
    assert resp.status_code == 400
    msg = resp.json().get("error") or resp.json().get("detail")
    assert "Only valid PDF" in msg


def test_upload_and_download_lifecycle(tmp_path, monkeypatch):
    from src.core.security import create_access_token
    token = create_access_token({"user_id": 1, "email": "pandeytoya22@gmail.com"})
    headers = {"Authorization": f"Bearer {token}"}

    import src.dashboard.routers.documents as doc_mod
    monkeypatch.setattr(doc_mod, "DOCS_DIR", str(tmp_path))

    # 1. Upload valid PDF
    pdf_bytes = b"%PDF-1.4 valid test pdf stream"
    pdf_b64 = base64.b64encode(pdf_bytes).decode()
    resp = client.post(
        "/api/documents/upload",
        headers=headers,
        json={"category": "other_certificates", "filename": "certs.pdf", "file_base64": pdf_b64},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["document"]["exists"] is True

    # 2. Download uploaded PDF
    dl_resp = client.get("/api/documents/download/other_certificates.pdf", headers=headers)
    assert dl_resp.status_code == 200
    assert dl_resp.content == pdf_bytes
