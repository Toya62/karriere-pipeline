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

    # 4. Unauthenticated guest visiting /api/funnel-stats -> zero stats, empty lists
    guest_funnel = client.get("/api/funnel-stats").json()
    assert guest_funnel["stages"]["total"] == 0
    assert guest_funnel["stages"]["applied"] == 0
    assert guest_funnel["ready_to_submit"] == []

    # 5. Unauthenticated guest visiting /api/datasets -> no candidate/combined queues
    guest_datasets = client.get("/api/datasets").json()
    assert "all_combined" not in guest_datasets
    assert "ai_approved" not in guest_datasets
    assert "linkedin" in guest_datasets

    # 6. Unauthenticated guest visiting /api/jobs?dataset=all_combined -> empty list
    guest_combined_jobs = client.get("/api/jobs?dataset=all_combined").json()
    assert guest_combined_jobs == []


def test_user_jobs_and_evaluations_isolation():
    from src.db.database import get_db_connection, setup_db

    setup_db("data/karriere.db")
    user_a_id, token_a = _create_user_and_token("Grace")
    user_b_id, token_b = _create_user_and_token("Heidi")

    # Seed a test job and evaluation in DB
    conn = get_db_connection("data/karriere.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("Acme Corp", "Senior Python Engineer", "https://acme.com/job/123", "Berlin", "Python FastAPI", "2026-11-08")
    )
    cur.execute("SELECT id FROM jobs WHERE url = 'https://acme.com/job/123'")
    job_id = cur.fetchone()[0]

    # Insert evaluation into user_jobs for Grace (user_a) only
    cur.execute(
        "INSERT OR REPLACE INTO user_jobs (user_id, job_id, status, score, chance, archetype, matched_skills, gaps, summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_a_id, job_id, "APPROVED (FIT: 92%)", 92, "HIGH", "backend_platform", "Python, FastAPI", "None", "Great fit")
    )
    conn.commit()
    conn.close()

    # Grace queries ai_approved -> sees Acme Corp with score 92
    resp_a = client.get("/api/jobs?dataset=ai_approved", headers={"Authorization": f"Bearer {token_a}"})
    assert resp_a.status_code == 200
    grace_jobs = resp_a.json()
    assert any(j["company"] == "Acme Corp" and j["score"] == 92 for j in grace_jobs)

    # Heidi queries ai_approved -> must NOT see Acme Corp (since Heidi has no approved jobs)
    resp_b = client.get("/api/jobs?dataset=ai_approved", headers={"Authorization": f"Bearer {token_b}"})
    assert resp_b.status_code == 200
    heidi_jobs = resp_b.json()
    assert not any(j["company"] == "Acme Corp" for j in heidi_jobs)

    # Unauthenticated guest queries ai_approved -> empty list
    resp_guest = client.get("/api/jobs?dataset=ai_approved")
    assert resp_guest.status_code == 200
    assert resp_guest.json() == []

