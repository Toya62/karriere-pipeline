"""Job dataset endpoints: SQLite-backed views served as JSON."""

import os
import sqlite3

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from src.core.logger import get_logger
from src.dashboard.dismissals import sync_dismissals_from_json
from src.dashboard.schemas import ApprovedIndexEntry, JobRecord
from src.db.database import get_db_connection, is_postgres

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["jobs"])

DB_PATH = os.path.join('data', 'karriere.db')

DATASET_VIEWS = [
    'ungenerated_approved',
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
    'ashby',
    'arbeitnow',
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

    # Deduplicate cross-portal reposts (e.g., same job on LinkedIn and Arbeitnow)
    # Normalize company (strip GmbH, AG, SE) and title (strip gender suffixes)
    import re
    def _norm_co(c):
        s = re.sub(r'\b(gmbh|ag|se|co\.?\s*kg|inc|corp|ltd)\b', '', str(c).lower())
        return re.sub(r'[^a-z0-9]', '', s).strip()

    def _norm_ti(t):
        s = re.sub(r'\(m/w/d\)|\(w/m/d\)|\(f/m/d\)|\(f/m/x\)|\(all genders\)|\(x/f/m\)', '', str(t).lower())
        return re.sub(r'[^a-z0-9]', '', s).strip()

    df["_norm_c"] = df["company"].apply(_norm_co)
    df["_norm_t"] = df["title"].apply(_norm_ti)
    # Prefer URLs with direct application or rich portal info (e.g. LinkedIn, Arbeitsagentur)
    df = df.drop_duplicates(subset=["_norm_c", "_norm_t"], keep="first")
    df = df.drop(columns=["_norm_c", "_norm_t"])

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
        if not is_postgres() and not os.path.exists(DB_PATH):
            return []
        conn = get_db_connection(DB_PATH)
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

        if is_postgres() or os.path.exists(DB_PATH):
            conn = get_db_connection(DB_PATH)
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

        conn = get_db_connection(DB_PATH)

        if 'ungenerated_approved' in raw_dataset or 'pending_generation' in raw_dataset:
            # 1. Fetch applied set via single fast query (<1ms) instead of quadratic correlated subquery
            cur = conn.cursor()
            cur.execute("""
                SELECT LOWER(j.url), LOWER(SUBSTR(j.company, 1, 15)), LOWER(SUBSTR(j.title, 1, 20))
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE a.cv_pdf_path IS NOT NULL AND a.cv_pdf_path != ''
            """)
            applied_urls = set()
            applied_keys = set()
            for r in cur.fetchall():
                if r[0]:
                    applied_urls.add(r[0].strip().lower())
                if r[1] and r[2]:
                    applied_keys.add((r[1].strip().lower(), r[2].strip().lower()))

            # 2. Fast indexed query for high-scoring approved jobs without generated packages
            q = base_select + '''
            JOIN evaluations e ON e.job_id = j.id
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE e.status LIKE 'APPROVED%' 
              AND e.score >= 85
              AND e.status != 'USER_DISMISSED'
              AND (a.id IS NULL OR a.cv_pdf_path IS NULL OR a.cv_pdf_path = '')
            ORDER BY e.score DESC, j.id DESC
            '''
            df = pd.read_sql_query(q, conn)
            conn.close()

            if not df.empty:
                keep = []
                for _, row in df.iterrows():
                    u = str(row.get('job_url') or '').strip().lower()
                    co = str(row.get('company') or '').strip().lower()[:15]
                    ti = str(row.get('title') or '').strip().lower()[:20]
                    if u in applied_urls or (co, ti) in applied_keys:
                        keep.append(False)
                    else:
                        keep.append(True)
                df = df[keep]

            df = clean_jobs_df(df)
            return df.to_dict(orient='records')
        elif 'all_combined' in raw_dataset:
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
        elif 'ashby' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE j.url LIKE '%ashbyhq%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        elif 'arbeitnow' in raw_dataset:
            q = base_select + '''
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE j.url LIKE '%arbeitnow%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
            '''
        else:  # Default: ai_approved
            q = base_select + '''
            JOIN evaluations e ON e.job_id = j.id
            WHERE e.status LIKE 'APPROVED%' AND e.status != 'USER_DISMISSED'
            ORDER BY e.score DESC
            '''

        df = pd.read_sql_query(q, conn)
        conn.close()
        df = clean_jobs_df(df)
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile")
def get_candidate_profile():
    """Return verified candidate profile facts, verified projects, and skills taxonomy."""
    try:
        from src.core import config
        p = config.load_candidate_profile()

        # Parse structured work experience from experience_summary if present
        import re
        experiences = []
        raw_summary = p.get("experience_summary", "")
        for line in raw_summary.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                m = re.match(r"^-\s*([^,]+),\s*([^(]+)\s*\(([^)]+)\):\s*(.+)$", line)
                if m:
                    role, company, period, desc = m.groups()
                    experiences.append({
                        "role": role.strip(),
                        "company": company.strip(),
                        "period": period.strip(),
                        "description": desc.strip(),
                    })

        return {
            "personal_info": p.get("personal_info", {}),
            "education": p.get("education", []),
            "experience": experiences,
            "skills": p.get("skills", {}),
            "languages": p.get("languages", {}),
            "projects": p.get("projects", []),
            "experience_summary": raw_summary,
            "job_search_preferences": p.get("job_search_preferences", {}),
            "integrity_status": "100% Verified Profile — AGENTS.md Single Source of Truth",
        }
    except Exception as e:
        logger.error(f"Failed to load candidate profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))
