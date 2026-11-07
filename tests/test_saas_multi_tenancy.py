"""Unit tests for SaaS multi-tenant isolation across candidate profiles, custom fields, and documents."""

import base64
import uuid
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app

client = TestClient(create_app())


def _create_user_and_token(name: str) -> tuple[int, str]:
    email = f"{name.lower()}_{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123!", "full_name": name},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["user"]["id"], data["token"]


def test_candidate_profile_isolation():
    _, token_a = _create_user_and_token("Alice")
    _, token_b = _create_user_and_token("Bob")

    # 1. Alice updates her profile
    alice_profile = {
        "personal_info": {"name": "Alice Wonderland", "email": "alice@wonderland.com"},
        "education": [{"degree": "B.Sc. CS", "institution": "TU Berlin"}],
        "skills": {"Languages": ["Python", "Rust"]},
    }
    resp_a = client.put(
        "/api/profile",
        headers={"Authorization": f"Bearer {token_a}"},
        json=alice_profile,
    )
    assert resp_a.status_code == 200

    # 2. Bob reads his profile -> must NOT see Alice's data
    resp_b = client.get("/api/profile", headers={"Authorization": f"Bearer {token_b}"})
    assert resp_b.status_code == 200
    bob_data = resp_b.json()
    assert bob_data["personal_info"].get("name") != "Alice Wonderland"
    assert "Rust" not in str(bob_data.get("skills", {}))

    # 3. Alice reads her profile -> gets her exact data
    resp_a_read = client.get("/api/profile", headers={"Authorization": f"Bearer {token_a}"})
    assert resp_a_read.status_code == 200
    assert resp_a_read.json()["personal_info"]["name"] == "Alice Wonderland"


def test_learned_fields_isolation():
    _, token_a = _create_user_and_token("Carol")
    _, token_b = _create_user_and_token("Dan")

    # Carol saves custom fields
    client.post(
        "/api/profile/custom-fields",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"fields": {"salary_expectation": "85000", "notice_period": "3 months"}},
    )

    # Dan checks custom fields -> must be empty or Dan's own fields
    dan_fields = client.get(
        "/api/profile/custom-fields",
        headers={"Authorization": f"Bearer {token_b}"},
    ).json().get("fields", {})
    assert "salary_expectation" not in dan_fields

    # Carol checks custom fields -> sees her fields
    carol_fields = client.get(
        "/api/profile/custom-fields",
        headers={"Authorization": f"Bearer {token_a}"},
    ).json().get("fields", {})
    assert carol_fields.get("salary_expectation") == "85000"


def test_documents_isolation(tmp_path, monkeypatch):
    import src.dashboard.routers.documents as doc_mod
    monkeypatch.setattr(doc_mod, "DOCS_DIR", str(tmp_path))

    _, token_a = _create_user_and_token("Eve")
    _, token_b = _create_user_and_token("Frank")

    # Eve uploads transcripts
    eve_pdf = b"%PDF-1.4 Eve's private university transcript"
    b64_pdf = base64.b64encode(eve_pdf).decode()
    upload_resp = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"category": "transcripts", "file_base64": b64_pdf},
    )
    assert upload_resp.status_code == 200

    # Frank checks documents -> transcripts exists should be False
    frank_docs = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()["documents"]
    frank_transcripts = next(d for d in frank_docs if d["key"] == "transcripts")
    assert frank_transcripts["exists"] is False

    # Eve checks documents -> transcripts exists is True
    eve_docs = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()["documents"]
    eve_transcripts = next(d for d in eve_docs if d["key"] == "transcripts")
    assert eve_transcripts["exists"] is True


def test_guest_privacy_and_toyanath_pro_account():
    """Verify that unauthenticated guests see zero private details of Toyanath Pandey."""
    # 1. Unauthenticated guest visiting /api/profile -> ZERO details of Toyanath
    guest_profile = client.get("/api/profile").json()
    assert guest_profile["personal_info"].get("name") != "Toyanath Pandey"
    assert "Kerckhoff" not in str(guest_profile)
    assert "Ilmenau" not in str(guest_profile)

    # 2. Unauthenticated guest visiting /api/tracker -> empty list
    guest_tracker = client.get("/api/tracker").json()
    assert guest_tracker == []

    # 3. Unauthenticated guest visiting /api/auth/me -> user is null
    me_resp = client.get("/api/auth/me").json()
    assert me_resp["user"] is None
