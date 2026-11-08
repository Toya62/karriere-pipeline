import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from src.db.database import (
    setup_db,
    save_user_job_evaluation,
    create_user,
    save_jobs_to_db,
)
from src.ai.matcher import save_evaluations_to_db, run_gemini_matcher_on_db
import pandas as pd


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_karriere.db"
    conn = setup_db(str(db_file))
    conn.close()
    return str(db_file)


def test_save_user_job_evaluation_direct(test_db):
    user = create_user(
        email="test_eval@example.com",
        full_name="Test Evaluator",
        role="candidate",
        tier="pro",
        conn=setup_db(test_db),
    )
    user_id = user["id"]

    # Insert a dummy job
    df = pd.DataFrame([{
        "company": "PCL Construction",
        "title": "Project Coordinator",
        "url": "https://indeed.com/job/pcl123",
        "location": "Toronto, ON, Canada",
        "description": "Coordinate on-site civil engineering projects and submittals.",
        "scraped_at": "2026-11-08 12:00:00",
    }])
    save_jobs_to_db(df, db_path=test_db)

    conn = setup_db(test_db)
    cur = conn.cursor()
    cur.execute("SELECT id FROM jobs WHERE company = 'PCL Construction'")
    job_id = cur.fetchone()[0]

    # Save evaluation
    success = save_user_job_evaluation(
        user_id=user_id,
        job_id=job_id,
        status="APPROVED_STRONG_FIT",
        score=92,
        chance="HIGH",
        archetype="civil_engineering",
        matched_skills="Project Management, AutoCAD",
        gaps="None",
        summary="Excellent alignment with civil engineering background.",
        evaluated_at="2026-11-08 12:05:00",
        conn=conn,
    )
    assert success is True

    # Verify user_jobs entry exists
    cur.execute("SELECT status, score, archetype FROM user_jobs WHERE user_id = ? AND job_id = ?", (user_id, job_id))
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "APPROVED_STRONG_FIT"
    assert row[1] == 92
    assert row[2] == "civil_engineering"

    # Verify evaluations table (admin) was NOT touched
    cur.execute("SELECT 1 FROM evaluations WHERE job_id = ?", (job_id,))
    assert cur.fetchone() is None
    conn.close()


def test_save_evaluations_to_db_user_scoped(test_db):
    user = create_user(
        email="scoped@example.com",
        full_name="Scoped User",
        role="candidate",
        tier="pro",
        conn=setup_db(test_db),
    )
    user_id = user["id"]

    eval_records = [{
        "company": "EllisDon",
        "title": "Junior Estimator",
        "job_url": "https://indeed.com/job/ed456",
        "location": "Toronto, ON",
        "description": "Prepare quantity takeoffs and project cost estimates.",
        "scraped_at": "2026-11-08 12:00:00",
        "gemini_status": "APPROVED",
        "gemini_score": 88,
        "gemini_interview_chance": "HIGH",
        "target_archetype": "civil_engineering",
        "gemini_matched_skills": "Cost Estimation, Quantity Takeoff",
        "gemini_gaps": "Bluebeam",
        "gemini_summary": "Strong fit for Junior Estimator role.",
        "evaluated_at": "2026-11-08 12:10:00",
    }]

    save_evaluations_to_db(eval_records, db_path=test_db, user_id=user_id)

    conn = setup_db(test_db)
    cur = conn.cursor()
    cur.execute("SELECT uj.status, uj.score FROM user_jobs uj JOIN jobs j ON uj.job_id = j.id WHERE uj.user_id = ?", (user_id,))
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "APPROVED"
    assert row[1] == 88

    # Ensure evaluations table is empty for this job
    cur.execute("SELECT 1 FROM evaluations")
    assert cur.fetchone() is None
    conn.close()


def test_run_gemini_matcher_on_db_with_user_id(test_db):
    user = create_user(
        email="matcher_user@example.com",
        full_name="Matcher User",
        role="candidate",
        tier="pro",
        conn=setup_db(test_db),
    )
    user_id = user["id"]

    # Insert a job
    df = pd.DataFrame([{
        "company": "Aecon Group",
        "title": "Site Engineer",
        "url": "https://indeed.com/job/aecon789",
        "location": "Toronto, ON",
        "description": "Manage on-site civil works, inspections, and subcontractor reports.",
        "scraped_at": "2026-11-08 12:00:00",
    }])
    save_jobs_to_db(df, db_path=test_db)

    fake_profile = {
        "target_titles": ["Site Engineer", "Project Coordinator"],
        "archetype": "civil_engineering",
        "skills": ["AutoCAD", "Site Supervision"],
    }

    mock_eval = {
        "status": "APPROVED_STRONG_FIT",
        "is_approved": True,
        "match_score": 90,
        "interview_chance": "HIGH",
        "recommended_doc_language": "ENGLISH",
        "decision_summary": "Direct fit for civil site engineer.",
        "_ai_provider": "gemini",
        "target_archetype": "civil_engineering",
        "tech_stack_overlap": {
            "matched_verified_skills": ["Site Supervision"],
            "optional_or_learnable_gaps": [],
        },
    }

    with patch("src.ai.matcher.get_gemini_client", return_value=MagicMock()), \
         patch("src.ai.matcher.get_router_status", return_value={"providers": {"gemini": True}}), \
         patch("src.ai.matcher.evaluate_single_job", return_value=mock_eval) as mock_eval_fn:

        approved = run_gemini_matcher_on_db(
            db_path=test_db,
            user_id=user_id,
            candidate_profile=fake_profile,
            max_age_days=30,
        )

        assert len(approved) == 1
        assert mock_eval_fn.called
        assert mock_eval_fn.call_args[1].get("candidate_profile") == fake_profile

        # Verify results saved to user_jobs
        conn = setup_db(test_db)
        cur = conn.cursor()
        cur.execute("SELECT status, score FROM user_jobs WHERE user_id = ?", (user_id,))
        saved = cur.fetchone()
        assert saved is not None
        assert saved[0] == "APPROVED_STRONG_FIT"
        assert saved[1] == 90
        conn.close()

