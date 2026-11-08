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


def test_non_admin_portal_and_funnel_stats_zero_jobs():
    """Verify non-admin user sees 0 jobs across funnel stats and portal feeds when no user_jobs exist."""
    _, token_candidate = _create_user_and_token("CandidateZero")

    # Funnel stats must report 0 total_jobs, 0 pending, and empty harvest for this user
    stats_resp = client.get("/api/funnel-stats", headers={"Authorization": f"Bearer {token_candidate}"})
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["counts"]["total_jobs"] == 0
    assert stats["counts"]["pending_evaluations"] == 0
    assert stats["counts"]["total_approved"] == 0
    assert stats["portal_harvest"] == {}

    # All job datasets must return empty lists (zero leak of global scraped jobs)
    for feed in ("all_combined", "linkedin", "indeed", "xing", "bund", "ba", "personio", "arbeitnow"):
        resp = client.get(f"/api/jobs?file={feed}", headers={"Authorization": f"Bearer {token_candidate}"})
        assert resp.status_code == 200
        assert resp.json() == []


def test_admin_set_tier_endpoint():
    """Verify admin can promote a user to PRO, while non-admin gets 403."""
    from src.db.database import get_user_by_email, update_user
    from src.core.security import create_access_token

    # 1. Create candidate user
    cand_id, cand_token = _create_user_and_token("FreeCandidate")
    cand_user = client.get("/api/auth/me", headers={"Authorization": f"Bearer {cand_token}"}).json()["user"]
    assert cand_user["tier"] == "free"

    # 2. Candidate attempts to promote themselves -> 403 Forbidden
    self_resp = client.post(
        "/api/auth/set-tier",
        headers={"Authorization": f"Bearer {cand_token}"},
        json={"email": cand_user["email"], "tier": "pro"},
    )
    assert self_resp.status_code == 403

    # 3. Use admin user (Toyanath / user_id = 1)
    admin_user = get_user_by_email("pandeytoya22@gmail.com")
    if not admin_user:
        # Create or fetch admin in test env
        update_user(cand_id, {"role": "admin", "tier": "pro"})
        admin_token = cand_token
        # Create second user to promote
        cand_id, cand_token = _create_user_and_token("TargetCandidate")
        cand_user = client.get("/api/auth/me", headers={"Authorization": f"Bearer {cand_token}"}).json()["user"]
    else:
        admin_token = create_access_token({"user_id": admin_user["id"], "email": admin_user["email"], "role": "admin"})

    # 4. Admin promotes candidate to pro
    admin_resp = client.post(
        "/api/auth/set-tier",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": cand_user["email"], "tier": "pro"},
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json()["tier"] == "pro"

    # 5. Candidate checks me -> tier is pro
    cand_check = client.get("/api/auth/me", headers={"Authorization": f"Bearer {cand_token}"}).json()["user"]
    assert cand_check["tier"] == "pro"


def test_global_tenants_toronto_vs_berlin_jobs():
    """Verify international multi-tenant candidate isolation across portal routing and job filtering."""
    from src.core.dynamic_filters import UserFilterContext, filter_job_for_user
    from src.scrapers.query_builder import get_candidate_eligible_portals

    # 1. Candidate in Toronto, Canada
    _, token_toronto = _create_user_and_token("TorontoUser")
    toronto_profile = {
        "personal_info": {"name": "Toronto Candidate", "location": "Toronto, ON, Canada"},
        "target_titles": ["Software Engineer"],
        "job_search_preferences": {
            "countries": ["Canada"],
            "cities": ["Toronto"],
            "titles": ["Software Engineer"],
        },
    }
    client.put("/api/profile", headers={"Authorization": f"Bearer {token_toronto}"}, json=toronto_profile)

    # 2. Candidate in Berlin, Germany
    _, token_berlin = _create_user_and_token("BerlinUser")
    berlin_profile = {
        "personal_info": {"name": "Berlin Candidate", "location": "Berlin, Germany"},
        "target_titles": ["Software Engineer"],
        "job_search_preferences": {
            "countries": ["Germany"],
            "cities": ["Berlin"],
            "titles": ["Software Engineer"],
        },
    }
    client.put("/api/profile", headers={"Authorization": f"Bearer {token_berlin}"}, json=berlin_profile)

    # 3. Portal routing verification
    toronto_portals = get_candidate_eligible_portals(toronto_profile)
    assert "bund" not in toronto_portals
    assert "ba" not in toronto_portals
    assert "xing" not in toronto_portals
    assert "linkedin" in toronto_portals
    assert "indeed" in toronto_portals

    berlin_portals = get_candidate_eligible_portals(berlin_profile)
    assert "bund" in berlin_portals
    assert "ba" in berlin_portals
    assert "xing" in berlin_portals

    # 4. Filter evaluation verification
    toronto_ctx = UserFilterContext.from_profile(toronto_profile)
    berlin_ctx = UserFilterContext.from_profile(berlin_profile)

    job_ca = {
        "title": "Software Engineer",
        "company": "Shopify",
        "location": "Toronto, ON, Canada",
        "description": "Looking for a Software Engineer with Python experience.",
    }
    job_de = {
        "title": "Software Engineer",
        "company": "SAP",
        "location": "Berlin, Germany",
        "description": "Software Engineer für Cloud Plattformen gesucht.",
    }

    # Toronto candidate accepts Canada job, rejects Berlin job
    app_to_ca, _ = filter_job_for_user(job_ca, toronto_ctx)
    app_to_de, reason_to_de = filter_job_for_user(job_de, toronto_ctx)
    assert app_to_ca is True
    assert app_to_de is False
    assert "location" in reason_to_de.lower()

    # Berlin candidate accepts Berlin job, rejects Canada job
    app_be_de, _ = filter_job_for_user(job_de, berlin_ctx)
    app_be_ca, reason_be_ca = filter_job_for_user(job_ca, berlin_ctx)
    assert app_be_de is True
    assert app_be_ca is False
    assert "location" in reason_be_ca.lower()



