"""Job dataset endpoints: SQLite-backed views served as JSON."""

import os
import sqlite3

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from src.core.logger import get_logger
from src.dashboard.dismissals import sync_dismissals_from_json
from src.dashboard.schemas import ApprovedIndexEntry, JobRecord

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["jobs"])

DB_PATH = os.path.join('data', 'karriere.db')

DATASET_VIEWS = [
    'ai_approved',
    'all_combined',
    'best_jobs',
    'filtered_out',
    'linkedin',
    'indeed',
    'xing',
    'bund',
    'ba',
    'personio',
]


def clean_jobs_df(df):
    """Normalize columns, fill missing dates (LinkedIn fallback), and cast types."""
    from datetime import datetime

    if df.empty:
        return df

    standard_cols = {
        "title": "",
        "company": "Unknown Company",
        "location": "Germany",
        "date_posted": "",
        "first_seen": "",
        "scraped_at": "",
        "score": 0,
        "matched_skills": "",
        "ai_score": "",
        "ai_reason": "",
        "job_url": "",
        "description": "",
    }

    if "match_score" in df.columns:
        if "score" in df.columns:
            df["score"] = df["score"].fillna(df["match_score"])
            df = df.drop(columns=["match_score"])
        else:
            df = df.rename(columns={"match_score": "score"})

    # Cross-fill first_seen <-> date_posted only when the other column has a
    # real value. Never invent today's date for a job that has no timestamp
    # at all — doing so made 1,189 un-dated rows appear under "Today Only".
    if "first_seen" in df.columns:
        df["first_seen"] = df["first_seen"].replace(r'^\s*$', pd.NA, regex=True)
    else:
        df["first_seen"] = pd.NA
    if "date_posted" in df.columns:
        df["date_posted"] = df["date_posted"].replace(r'^\s*$', pd.NA, regex=True)
    else:
        df["date_posted"] = pd.NA
    df["first_seen"] = df["first_seen"].fillna(df["date_posted"])
    df["date_posted"] = df["date_posted"].fillna(df["first_seen"])

    for col, default_val in standard_cols.items():
        if col not in df.columns:
            df[col] = default_val
        else:
            df[col] = df[col].fillna(default_val)

    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
    return df.astype(object).where(pd.notnull(df), None)


@router.get("/files", response_model=list[str])
@router.get("/datasets", response_model=list[str])
def list_datasets():
    """Return the queryable SQLite-backed dataset view names."""
    return DATASET_VIEWS


@router.get("/approved-index", response_model=list[ApprovedIndexEntry])
def approved_index():
    """Lightweight index of approved jobs for client-side lookups."""
    try:
        if not os.path.exists(DB_PATH):
            return []
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT j.title, j.company, j.url
            FROM jobs j
            JOIN evaluations e ON e.job_id = j.id
            WHERE e.status LIKE 'APPROVED%' AND e.status != 'USER_DISMISSED'
        """)
        rows = [{"title": r[0], "company": r[1], "job_url": r[2]} for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job-descriptions")
def job_descriptions(
    urls: str = Query(""),
    company: str = Query(""),
    position: str = Query(""),
):
    """Resolve job descriptions by URL, falling back to (company, position)."""
    try:
        company = company.strip()
        position = position.strip()
        target_urls = [u.strip() for u in urls.split(',') if u.strip()]
        desc_map = {}

        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            if target_urls:
                placeholders = ','.join(['?'] * len(target_urls))
                query = f"SELECT url, description FROM jobs WHERE url IN ({placeholders})"
                cursor.execute(query, target_urls)
                for url, desc in cursor.fetchall():
                    if url and desc:
                        desc_map[url] = desc

            if (not desc_map or not any(desc_map.values())) and company and position:
                cursor.execute(
                    "SELECT description FROM jobs WHERE company = ? AND title = ? "
                    "AND description IS NOT NULL AND description != ''",
                    (company, position),
                )
                r = cursor.fetchone()
                if r and r[0]:
                    desc_map['_found_by_comp_pos'] = r[0]
                    if urls:
                        desc_map[urls] = r[0]

            conn.close()

        return desc_map
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs", response_model=list[JobRecord])
def list_jobs(
    file: str | None = Query(None),
    dataset: str | None = Query(None),
):
    """Return job records for a named SQLite view."""
    if not os.path.exists(DB_PATH):
        return []

    try:
        sync_dismissals_from_json(DB_PATH)
        raw_dataset = (file or dataset or 'ai_approved').lower()

        base_select = '''
        SELECT j.company, j.title, j.url as job_url, j.location, j.scraped_at,
               j.scraped_at as date_posted, j.scraped_at as first_seen,
               COALESCE(e.status, 'UNMATCHED') as gemini_status,
               COALESCE(e.score, 0) as score,
               COALESCE(e.score, 0) as gemini_score,
               COALESCE(e.chance, 'LOW') as gemini_interview_chance,
               COALESCE(e.archetype, '') as target_archetype,
               COALESCE(e.matched_skills, '') as gemini_matched_skills,
               COALESCE(e.gaps, '') as gemini_gaps,
               COALESCE(e.summary, '') as gemini_summary,
               e.evaluated_at
        FROM jobs j
        '''

        if 'all_combined' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        elif 'best_jobs' in raw_dataset:
            q = base_select + '''
            JOIN evaluations e ON e.job_id = j.id
            WHERE e.status LIKE 'APPROVED%' AND e.score >= 40 AND e.status != 'USER_DISMISSED'
            ORDER BY e.score DESC
            '''
        elif 'filtered_out' in raw_dataset or 'disqualified' in raw_dataset:
            q = base_select + '''
            JOIN evaluations e ON e.job_id = j.id
            WHERE e.status LIKE 'REJECTED%' AND e.status != 'USER_DISMISSED'
            ORDER BY e.evaluated_at DESC
            '''
        elif 'linkedin' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE (j.url LIKE '%linkedin.com%' OR j.url LIKE '%licdn%') AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        elif 'indeed' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE j.url LIKE '%indeed.%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        elif 'xing' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE j.url LIKE '%xing.com%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        elif 'bund' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE (j.url LIKE '%bund.de%' OR j.url LIKE '%interamt.de%') AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        elif 'ba' in raw_dataset or 'arbeitsagentur' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE j.url LIKE '%arbeitsagentur.de%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        elif 'personio' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE j.url LIKE '%personio%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        else:  # Default: ai_approved
            q = base_select + '''
            JOIN evaluations e ON e.job_id = j.id
            WHERE e.status LIKE 'APPROVED%' AND e.status != 'USER_DISMISSED'
            ORDER BY e.score DESC
            '''

        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(q, conn)
        conn.close()
        df = clean_jobs_df(df)
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
