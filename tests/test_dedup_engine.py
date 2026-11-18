import os
import sqlite3
import pandas as pd
import pytest

from src.core.dedup import (
    canonical_job_url,
    compute_jaccard_similarity,
    dedup_job_dataframe,
    extract_location_key,
    extract_location_tokens,
    extract_req_id,
    extract_title_tokens,
    normalize_company_entity,
    normalize_title_entity,
    plain_url,
    JobDedupIndex,
)
from src.core.utils import _normalize_company
from src.db.database import save_jobs_to_db, setup_db
from src.core.filters import filter_against_existing_catalog


# ---------------------------------------------------------------------------
# Bug 1 Tests: normalize_company_entity must not over-strip corporate nouns
# ---------------------------------------------------------------------------

def test_company_normalizer_preserves_corporate_nouns():
    """Bug 1: Different companies like 'Software Systems GmbH' and 'Software Technologies AG'
    must NOT be collapsed into 'software'."""
    comp1 = normalize_company_entity("Software Systems GmbH")
    comp2 = normalize_company_entity("Software Technologies AG")
    comp3 = normalize_company_entity("Software Solutions SE")
    comp4 = normalize_company_entity("Alpha Group GmbH")

    assert comp1 == "software systems"
    assert comp2 == "software technologies"
    assert comp3 == "software solutions"
    assert comp4 == "alpha group"

    assert comp1 != comp2
    assert comp2 != comp3
    assert comp1 != comp3


def test_company_normalizer_strips_legal_and_branch_parentheticals():
    """Legal suffixes and parenthetical annotations should still be cleanly stripped."""
    assert normalize_company_entity("aconium GmbH (Hauptsitz Berlin)") == "aconium"
    assert normalize_company_entity("aconium GmbH") == "aconium"
    assert normalize_company_entity("Statistisches Bundesamt (Destatis)") == "statistisches bundesamt"
    assert normalize_company_entity("Advantest Europe GmbH") == "advantest europe"
    assert normalize_company_entity("Siemens AG & Co. KGaA") == "siemens"


# ---------------------------------------------------------------------------
# Bug 2 Tests: DB-level URL deduplication & tracking parameter strip
# ---------------------------------------------------------------------------

def test_canonical_job_url_strips_tracking_and_apply_subpaths():
    """Bug 2 & Pitch 3: Strip utm_*, ref, source, and apply endpoints while preserving IDs."""
    raw1 = "https://example.com/jobs/123?utm_source=linkedin&utm_medium=feed&ref=feed"
    raw2 = "https://example.com/jobs/123"
    raw3 = "https://example.com/jobs/123/apply"
    raw4 = "[Python Dev](https://example.com/jobs/123?trackingId=xyz)"

    assert canonical_job_url(raw1) == "https://example.com/jobs/123"
    assert canonical_job_url(raw2) == "https://example.com/jobs/123"
    assert canonical_job_url(raw3) == "https://example.com/jobs/123"
    assert canonical_job_url(raw4) == "https://example.com/jobs/123"

    # Preserves essential job ID query parameters
    greenhouse_url = "https://boards.greenhouse.io/company/jobs?gh_jid=456789&utm_campaign=spring"
    assert canonical_job_url(greenhouse_url) == "https://boards.greenhouse.io/company/jobs?gh_jid=456789"


def test_db_save_jobs_dedups_by_canonical_url(tmp_path):
    """Bug 2: save_jobs_to_db must detect duplicates with tracking parameters and avoid double inserts."""
    test_db = str(tmp_path / "test_url_dedup.db")

    batch1 = pd.DataFrame([{
        "company": "Tech Corp",
        "title": "Backend Developer",
        "job_url": "https://techcorp.com/careers/42",
        "location": "Berlin",
        "description": "Short description.",
        "scraped_at": "2026-11-01",
    }])
    saved1 = save_jobs_to_db(batch1, db_path=test_db)
    assert saved1 == 1

    # Second scrape with tracking parameters on the same job URL
    batch2 = pd.DataFrame([{
        "company": "Tech Corp GmbH",  # Slightly different company string
        "title": "Backend Developer (m/w/d)",
        "job_url": "https://techcorp.com/careers/42?utm_source=linkedin&refId=abc",
        "location": "Berlin",
        "description": "A much richer and longer description for backend developer role.",
        "scraped_at": "2026-11-02",
    }])
    saved2 = save_jobs_to_db(batch2, db_path=test_db)
    assert saved2 == 0  # Deduplicated!

    conn = setup_db(test_db)
    cur = conn.cursor()
    cur.execute("SELECT count(*), description FROM jobs WHERE url LIKE '%techcorp.com/careers/42%'")
    row = cur.fetchone()
    conn.close()

    assert row[0] == 1  # Only 1 record in DB
    assert "much richer and longer description" in row[1]  # Enriched with richer description!


# ---------------------------------------------------------------------------
# Bug 3 Tests: DB-level fuzzy location + title matching
# ---------------------------------------------------------------------------

def test_db_save_jobs_fuzzy_location_title_match(tmp_path):
    """Bug 3: Jobs slipping through with differing agency/formatting in same city are caught at DB level."""
    test_db = str(tmp_path / "test_fuzzy_db.db")

    batch1 = pd.DataFrame([{
        "company": "Agency Alpha",
        "title": "Senior Cloud Data Infrastructure Engineer",
        "job_url": "https://portal-a.com/job/100",
        "location": "München, Deutschland",
        "description": "Cloud data infra job",
        "scraped_at": "2026-11-01",
    }])
    saved1 = save_jobs_to_db(batch1, db_path=test_db)
    assert saved1 == 1

    # Differing agency post in Munich for the same position
    batch2 = pd.DataFrame([{
        "company": "Recruiting Beta GmbH",
        "title": "Senior Cloud Data Infrastructure Developer (m/w/d)",
        "job_url": "https://portal-b.com/job/200",
        "location": "80331 München",  # Same city via PLZ / city matching
        "description": "Identical client position",
        "scraped_at": "2026-11-02",
    }])
    saved2 = save_jobs_to_db(batch2, db_path=test_db)
    assert saved2 == 0  # Caught by fuzzy title token Jaccard + location match!

    conn = setup_db(test_db)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM jobs")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 1


# ---------------------------------------------------------------------------
# Bug 4 Tests: Title variation & synonym mapping
# ---------------------------------------------------------------------------

def test_title_normalizer_maps_synonyms_and_compounds():
    """Bug 4 & Pitch 5: Map Engineer ↔ Developer ↔ Entwickler and German compound roles."""
    t1 = normalize_title_entity("Software Engineer (m/w/d)")
    t2 = normalize_title_entity("Software Developer (all genders)")
    t3 = normalize_title_entity("Softwareentwickler (m/w/d)")

    assert t1 == "software developer"
    assert t2 == "software developer"
    assert t3 == "software developer"
    assert t1 == t2 == t3

    # Compound roles
    assert normalize_title_entity("Backend-Entwickler (gn)") == "backend developer"
    assert normalize_title_entity("Frontend Entwicklerin (w/m/d)") == "frontend developer"
    assert normalize_title_entity("Data Engineer (f/m/d)") == "data developer"


# ---------------------------------------------------------------------------
# Bug 5 Tests: Single unified company normalizer
# ---------------------------------------------------------------------------

def test_unified_company_normalizer_consistency():
    """Bug 5: _normalize_company and normalize_company_entity must behave consistently."""
    raw = "Bosch Mobility Solutions GmbH (Hauptsitz Stuttgart)"
    norm1 = normalize_company_entity(raw)
    norm2 = _normalize_company(raw)

    assert norm1 == norm2 == "bosch mobility solutions"


# ---------------------------------------------------------------------------
# Bug 6 Tests: Location key extraction handles streets vs cities
# ---------------------------------------------------------------------------

def test_location_extractor_extracts_plz_or_city():
    """Bug 6: Addresses with street prefixes must extract city or PLZ, not the street."""
    # City name takes priority over PLZ when both present, while tokens extract both
    assert extract_location_key("Theodor-Heuss-Allee 108, 60486 Frankfurt am Main") == "frankfurt am main"
    assert "60486" in extract_location_tokens("Theodor-Heuss-Allee 108, 60486 Frankfurt am Main")
    assert extract_location_key("51427 Bergisch Gladbach") == "bergisch gladbach"
    assert "51427" in extract_location_tokens("51427 Bergisch Gladbach")
    assert extract_location_key("51427") == "51427"

    # When no PLZ is present, extracts the city segment, not the street name
    assert extract_location_key("Theodor-Heuss-Allee 108, Frankfurt am Main") == "frankfurt am main"
    assert extract_location_key("Frankfurt am Main, Deutschland") == "frankfurt am main"
    assert extract_location_key("Essen, Nordrhein-Westfalen") == "essen"
    assert extract_location_key("Berlin / Remote") == "berlin"


# ---------------------------------------------------------------------------
# Bug 7 Tests: DataFrame and Catalog Dedup Integration
# ---------------------------------------------------------------------------

def test_dedup_job_dataframe_multi_tier():
    """Bug 7 & Pitch 6: Unified 5-tier deduplication pipeline on DataFrames."""
    df = pd.DataFrame([
        # Row 0: Original
        {
            "company": "Zalando SE",
            "title": "Software Engineer (m/w/d)",
            "job_url": "https://jobs.zalando.com/1",
            "location": "Berlin",
            "description": "Short desc",
        },
        # Row 1: Duplicate by canonical URL (with utm params)
        {
            "company": "Zalando",
            "title": "Software Engineer",
            "job_url": "https://jobs.zalando.com/1?utm_source=linkedin",
            "location": "Berlin",
            "description": "Longer description with rich information about the team.",
        },
        # Row 2: Duplicate by requisition ID
        {
            "company": "Zalando",
            "title": "Software Engineer II",
            "job_url": "https://other.portal/job/99",
            "location": "Berlin",
            "description": "Referenznummer: REQ12345-01 for Zalando role",
        },
        {
            "company": "Zalando Group",
            "title": "Software Engineer - Payments",
            "job_url": "https://third.portal/job/100",
            "location": "Berlin",
            "description": "Ausschreibung Kennziffer REQ12345-99",
        },
        # Row 3: Completely distinct job
        {
            "company": "BMW Group",
            "title": "C++ Embedded Engineer",
            "job_url": "https://bmw.com/jobs/55",
            "location": "München",
            "description": "Embedded C++ role",
        },
    ])

    deduped = dedup_job_dataframe(df, keep_longest_desc=True)
    # Row 0 and Row 1 collapse into 1 (Row 1 has longer description so it wins)
    # Row 2 and Row 3 collapse by req ID (REQ12345)
    # BMW distinct job remains
    assert len(deduped) == 3
    urls = list(deduped["job_url"])
    assert "https://jobs.zalando.com/1?utm_source=linkedin" in urls
    assert "https://bmw.com/jobs/55" in urls


def test_filter_against_existing_catalog_with_unified_dedup(tmp_path):
    """Catalog filtering catches cross-portal duplicates via canonical URL and entity keys."""
    test_db = str(tmp_path / "test_cat.db")
    conn = setup_db(test_db)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO jobs (company, title, url, location, description, scraped_at)
        VALUES ('Infineon Technologies AG', 'DevOps Engineer (m/w/d)', 'https://infineon.com/job/10', 'Dresden', 'Desc 1', '2026-11-01')
    """)
    conn.commit()
    conn.close()

    new_jobs = pd.DataFrame([
        # Duplicate by canonical entity (DevOps Engineer ↔ DevOps Developer)
        {
            "company": "Infineon Technologies",
            "title": "DevOps Developer (all genders)",
            "job_url": "https://linkedin.com/job/infineon-devops",
            "description": "Desc 1",
        },
        # Duplicate by canonical URL with query tracking
        {
            "company": "Other",
            "title": "Other",
            "job_url": "https://infineon.com/job/10?utm_source=stepstone",
            "description": "Desc 2",
        },
        # Genuine new job
        {
            "company": "Bosch",
            "title": "Embedded Linux Developer",
            "job_url": "https://bosch.com/jobs/77",
            "description": "Desc 3",
        },
    ])

    filtered = filter_against_existing_catalog(new_jobs, catalog_files=[], db_path=test_db)
    assert len(filtered) == 1
    assert filtered.iloc[0]["company"] == "Bosch"
