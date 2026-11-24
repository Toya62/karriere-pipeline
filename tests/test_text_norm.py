# tests/test_text_norm.py
"""Bug #9: scraper normalisation on ingest — 'nan' -> empty, markdown
stripped, skill dedup; ingest gate flags empty-location rows."""
import os

os.environ["DATABASE_URL"] = ""

import logging
import uuid

import pandas as pd
import pytest

from src.ai.matcher import save_evaluations_to_db
from src.core.text_norm import (
    clean_text_block,
    clean_text_field,
    fix_known_typos,
    normalize_skills,
    strip_markdown,
)
from src.db.database import (
    create_scraper_run,
    create_user,
    get_db_connection,
    save_jobs_to_db,
    save_user_job_evaluation,
    setup_db,
)


def test_clean_text_field_drops_nan_literals():
    assert clean_text_field("nan") == ""
    assert clean_text_field("NaN") == ""
    assert clean_text_field("NAN") == ""
    assert clean_text_field(None) == ""
    assert clean_text_field(float("nan")) == ""
    assert clean_text_field("None") == ""
    assert clean_text_field("null") == ""
    assert clean_text_field("  Siemens   AG  ") == "Siemens AG"
    assert clean_text_field("Acme GmbH") == "Acme GmbH"


def test_clean_text_block_keeps_line_breaks():
    assert clean_text_block("nan") == ""
    assert clean_text_block(None) == ""
    assert clean_text_block("line one\n\nline two") == "line one\n\nline two"


def test_strip_markdown():
    assert strip_markdown(r"Fix \& \- \. here") == "Fix & - . here"
    assert strip_markdown("Use **bold** and __strong__ text") == "Use bold and strong text"
    assert strip_markdown("An *italic* word") == "An italic word"
    assert strip_markdown("See [the posting](https://example.com/jobs/1)") == "See the posting"
    assert strip_markdown("## About the role\nDo things") == "About the role\nDo things"
    assert strip_markdown("Intro ## Head here") == "Intro Head here"
    assert strip_markdown("C# Developer wanted") == "C# Developer wanted"
    assert strip_markdown("* first\n- second\n+ third") == "first\nsecond\nthird"
    # Unmatched markers and '*' as an operator are left alone.
    assert strip_markdown("5 * 8 = 40") == "5 * 8 = 40"
    assert strip_markdown("plain text, no markdown") == "plain text, no markdown"


def test_normalize_skills_dedupes_variants():
    assert normalize_skills("C++, C/C++, Python, python, nan, , React") == "C++, Python, React"
    assert normalize_skills("C / C++") == "C++"
    assert normalize_skills("c++") == "C++"
    assert normalize_skills("Python; Java, python") == "Python, Java"
    assert normalize_skills("") == ""
    assert normalize_skills(None) == ""
    # C and C++ are distinct skills — both kept.
    assert normalize_skills("C, C++") == "C, C++"


def test_fix_known_typos():
    assert fix_known_typos("Senior Engineeer (m/w/d)") == "Senior Engineer (m/w/d)"
    assert fix_known_typos("nothing to fix here") == "nothing to fix here"


@pytest.fixture(scope="module")
def seeded_user():
    setup_db()
    uid = uuid.uuid4().hex[:8]
    user = create_user(
        email=f"textnorm_test_{uid}@example.com",
        hashed_password="x" * 10,
        full_name="Text Norm Test User",
        role="candidate",
        tier="pro",
        is_verified=True,
    )
    run_id = create_scraper_run(user_id=user["id"], portal="indeed", days=1, queries="ml")
    return {"user_id": user["id"], "run_id": run_id, "uid": uid}


def _jobs_for_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT company, title, location, description FROM jobs WHERE scraped_by_user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def test_ingest_gate_and_normalisation(seeded_user, caplog):
    """Bug #9: 'nan' company row is rejected; 'nan'/empty location rows are
    stored but flagged (warning logged); markdown is stripped on ingest."""
    uid = seeded_user["uid"]
    user_id = seeded_user["user_id"]
    # Company + titles are uid-suffixed: the dedup entity tier matches on
    # company+title (ignoring URL), so fixed names would collide with rows
    # from earlier runs in the shared test DB and be skipped as duplicates.
    co = f"Acme {uid}"
    df = pd.DataFrame([
        # Literal "nan" company (pandas NaN leaking in) -> rejected.
        {"company": float("nan"), "title": f"Dev Nan {uid}", "url": f"https://example.com/nan-{uid}",
         "location": "Berlin", "description": "desc"},
        # Empty company -> rejected.
        {"company": "", "title": f"Dev Empty {uid}", "url": f"https://example.com/empty-{uid}",
         "location": "Berlin", "description": "desc"},
        # "nan" location -> stored with empty location + warning.
        {"company": co, "title": f"Dev A {uid}", "url": f"https://example.com/a-{uid}",
         "location": "nan", "description": "desc A"},
        # Empty location -> stored with empty location + warning.
        {"company": co, "title": f"Dev B {uid}", "url": f"https://example.com/b-{uid}",
         "location": "", "description": "desc B"},
        # Markdown escapes/formatting stripped from the description.
        {"company": co, "title": f"Dev C {uid}", "url": f"https://example.com/c-{uid}",
         "location": "Berlin",
         "description": r"Fix \& \- **bold** __x__ *it* [link](http://x) ## Head"},
        # Clean row passes through untouched.
        {"company": co, "title": f"Dev D {uid}", "url": f"https://example.com/d-{uid}",
         "location": "Munich", "description": "plain desc"},
        # Source typo is NOT corrected on ingest (cleanup script only).
        {"company": co, "title": f"Senior Engineeer {uid}", "url": f"https://example.com/e-{uid}",
         "location": "Berlin", "description": "desc E"},
    ])
    with caplog.at_level(logging.WARNING, logger="src.db.database"):
        saved = save_jobs_to_db(df, portal="indeed", run_id=seeded_user["run_id"], user_id=user_id)

    assert saved == 5
    rows = {(title): (company, location, desc) for company, title, location, desc in _jobs_for_user(user_id)}
    assert f"Dev Nan {uid}" not in rows
    assert f"Dev Empty {uid}" not in rows
    assert rows[f"Dev A {uid}"] == (co, "", "desc A")
    assert rows[f"Dev B {uid}"] == (co, "", "desc B")
    assert rows[f"Dev C {uid}"] == (co, "Berlin", "Fix & - bold x it link Head")
    assert rows[f"Dev D {uid}"] == (co, "Munich", "plain desc")
    assert rows[f"Senior Engineeer {uid}"][0] == co  # typo kept on ingest
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("empty location" in r.message for r in warnings), "empty-location row was not flagged"
    assert any("empty company/title" in r.message for r in warnings)


def test_matcher_normalises_skills_on_write(seeded_user):
    """Bug #9: C++ / C/C++ duplicates collapse to one C++ when the matcher
    saves an evaluation."""
    uid = seeded_user["uid"]
    user_id = seeded_user["user_id"]
    record = {
        "company": "Skill Co",
        "title": f"Dev Skills {uid}",
        "job_url": f"https://example.com/skills-{uid}",
        "location": "Berlin",
        "description": "desc",
        "scraped_at": "",
        "gemini_status": "APPROVED",
        "gemini_score": 90,
        "gemini_interview_chance": "high",
        "target_archetype": "python_systems",
        "gemini_matched_skills": "C++, C/C++, Python, python, nan",
        "gemini_gaps": "",
        "gemini_summary": "good fit",
        "evaluated_at": "2026-11-23",
    }
    save_evaluations_to_db([record], user_id=user_id)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT matched_skills FROM user_jobs WHERE user_id = ? AND job_id IN "
        "(SELECT id FROM jobs WHERE title = ?)",
        (user_id, record["title"]),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "C++, Python"


def test_save_user_job_evaluation_normalises_skills(seeded_user):
    """Bug #9: the DB-layer evaluation write path also dedupes skills."""
    uid = seeded_user["uid"]
    user_id = seeded_user["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM jobs WHERE url = ?", (f"https://example.com/d-{uid}",))
    job = cur.fetchone()
    conn.close()
    assert job is not None
    save_user_job_evaluation(
        user_id=user_id, job_id=job[0], status="APPROVED", score=88,
        matched_skills="React, react, C / C++, C++",
    )
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT matched_skills FROM user_jobs WHERE user_id = ? AND job_id = ?",
        (user_id, job[0]),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "React, C++"
