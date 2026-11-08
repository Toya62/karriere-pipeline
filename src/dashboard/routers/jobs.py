"""Job dataset endpoints: SQLite-backed views served as JSON."""

import json
import os
import sqlite3
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.logger import get_logger
from src.dashboard.dismissals import sync_dismissals_from_json
from src.dashboard.routers.auth import get_current_user
from src.dashboard.schemas import ApprovedIndexEntry, CustomFieldsRequest, JobRecord
from src.db.database import (
    get_db_connection,
    get_user_learned_fields,
    get_user_profile,
    is_postgres,
    save_user_learned_fields,
    save_user_profile,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["jobs"])

DB_PATH = os.path.join('data', 'karriere.db')

CANDIDATE_DATASET_VIEWS = [
    'ungenerated_approved',
    'ai_approved',
    'all_combined',
    'best_jobs',
    'filtered_out',
]

PORTAL_DATASET_VIEWS = [
    'linkedin',
    'indeed',
    'xing',
    'bund',
    'ba',
    'personio',
    'ashby',
    'greenhouse',
    'arbeitnow',
]

DATASET_VIEWS = CANDIDATE_DATASET_VIEWS + PORTAL_DATASET_VIEWS


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
def list_datasets(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return the queryable dataset view names scoped to authentication state."""
    user_id = current_user.get("id", 0)
    if user_id <= 0:
        return PORTAL_DATASET_VIEWS
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
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Return job records for a named SQLite/Postgres view, scoped to calling user."""
    if not is_postgres() and not os.path.exists(DB_PATH):
        return []

    try:
        sync_dismissals_from_json(DB_PATH)
        raw_dataset = (file or dataset or 'ai_approved').lower()
        user_id = current_user.get("id", 0)

        conn = get_db_connection(DB_PATH)

        # Check if user_jobs exists (multi-tenant SaaS mode vs legacy single-user DB)
        has_user_jobs = False
        try:
            chk = conn.cursor()
            chk.execute("SELECT 1 FROM user_jobs LIMIT 1")
            has_user_jobs = True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

        # In multi-tenant SaaS mode, unauthenticated guests see zero evaluated/approved feeds
        if has_user_jobs and user_id <= 0:
            eval_only_datasets = (
                'ungenerated_approved',
                'pending_generation',
                'ai_approved',
                'all_combined',
                'best_jobs',
                'filtered_out',
                'disqualified',
            )
            if any(k in raw_dataset for k in eval_only_datasets):
                conn.close()
                return []

            # Public unauthenticated view: raw scraped jobs, no private match scores
            base_select = '''
            SELECT j.company, j.title, j.url as job_url, j.location, j.scraped_at,
                   j.scraped_at as date_posted, j.scraped_at as first_seen,
                   'UNMATCHED' as gemini_status,
                   0 as score,
                   0 as gemini_score,
                   'LOW' as gemini_interview_chance,
                   '' as target_archetype,
                   '' as gemini_matched_skills,
                   '' as gemini_gaps,
                   '' as gemini_summary,
                   NULL as evaluated_at
            FROM jobs j
            '''
            portal_cond = "1=1"
            if 'linkedin' in raw_dataset:
                portal_cond = "(j.url LIKE '%linkedin.com%' OR j.url LIKE '%licdn%')"
            elif 'indeed' in raw_dataset:
                portal_cond = "j.url LIKE '%indeed.%'"
            elif 'xing' in raw_dataset:
                portal_cond = "j.url LIKE '%xing.com%'"
            elif 'bund' in raw_dataset:
                portal_cond = "(j.url LIKE '%bund.de%' OR j.url LIKE '%interamt.de%')"
            elif 'ba' in raw_dataset or 'arbeitsagentur' in raw_dataset:
                portal_cond = "j.url LIKE '%arbeitsagentur.de%'"
            elif 'personio' in raw_dataset:
                portal_cond = "j.url LIKE '%personio%'"
            elif 'ashby' in raw_dataset:
                portal_cond = "j.url LIKE '%ashbyhq%'"
            elif 'greenhouse' in raw_dataset:
                portal_cond = "(j.url LIKE '%greenhouse.io%' OR j.url LIKE '%gh_jid%')"
            elif 'arbeitnow' in raw_dataset:
                portal_cond = "j.url LIKE '%arbeitnow%'"

            q = base_select + f" WHERE {portal_cond} ORDER BY j.id DESC LIMIT 100"
            df = pd.read_sql_query(q, conn)
            conn.close()
            df = clean_jobs_df(df)
            return df.to_dict(orient='records')

        eval_alias = "uj" if has_user_jobs else "e"
        base_select = f'''
        SELECT j.company, j.title, j.url as job_url, j.location, j.scraped_at,
               j.scraped_at as date_posted, j.scraped_at as first_seen,
               COALESCE({eval_alias}.status, 'UNMATCHED') as gemini_status,
               COALESCE({eval_alias}.score, 0) as score,
               COALESCE({eval_alias}.score, 0) as gemini_score,
               COALESCE({eval_alias}.chance, 'LOW') as gemini_interview_chance,
               COALESCE({eval_alias}.archetype, '') as target_archetype,
               COALESCE({eval_alias}.matched_skills, '') as gemini_matched_skills,
               COALESCE({eval_alias}.gaps, '') as gemini_gaps,
               COALESCE({eval_alias}.summary, '') as gemini_summary,
               {eval_alias}.evaluated_at
        FROM jobs j
        '''

        eval_join_inner = f"JOIN user_jobs uj ON uj.job_id = j.id AND uj.user_id = ?" if has_user_jobs else "JOIN evaluations e ON e.job_id = j.id"
        eval_join_left = f"LEFT JOIN user_jobs uj ON uj.job_id = j.id AND uj.user_id = ?" if has_user_jobs else "LEFT JOIN evaluations e ON e.job_id = j.id"
        user_param = [user_id] if has_user_jobs else []

        if 'ungenerated_approved' in raw_dataset or 'pending_generation' in raw_dataset:
            cur = conn.cursor()
            app_user_filter = "WHERE a.user_id = ?" if has_user_jobs else "WHERE 1=1"
            app_params = [user_id] if has_user_jobs else []
            cur.execute(f"""
                SELECT LOWER(j.url), LOWER(SUBSTR(j.company, 1, 15)), LOWER(SUBSTR(j.title, 1, 20))
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                {app_user_filter}
                AND a.cv_pdf_path IS NOT NULL AND a.cv_pdf_path != ''
            """, app_params)
            applied_urls = set()
            applied_keys = set()
            for r in cur.fetchall():
                if r[0]:
                    applied_urls.add(r[0].strip().lower())
                if r[1] and r[2]:
                    applied_keys.add((r[1].strip().lower(), r[2].strip().lower()))

            app_join_cond = "AND a.user_id = ?" if has_user_jobs else ""
            q = base_select + f'''
            {eval_join_inner}
            LEFT JOIN applications a ON a.job_id = j.id {app_join_cond}
            WHERE {eval_alias}.status LIKE 'APPROVED%' 
              AND {eval_alias}.score >= 85
              AND {eval_alias}.status != 'USER_DISMISSED'
              AND (a.id IS NULL OR a.cv_pdf_path IS NULL OR a.cv_pdf_path = '')
            ORDER BY {eval_alias}.score DESC, j.id DESC
            '''
            params = user_param + ([user_id] if has_user_jobs else [])
            df = pd.read_sql_query(q, conn, params=params if params else None)
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
            q = base_select + f'''
            {eval_join_left}
            WHERE COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'best_jobs' in raw_dataset:
            q = base_select + f'''
            {eval_join_inner}
            WHERE {eval_alias}.status LIKE 'APPROVED%' AND {eval_alias}.score >= 40 AND {eval_alias}.status != 'USER_DISMISSED'
            ORDER BY {eval_alias}.score DESC
            '''
            params = user_param
        elif 'filtered_out' in raw_dataset or 'disqualified' in raw_dataset:
            q = base_select + f'''
            {eval_join_inner}
            WHERE {eval_alias}.status LIKE 'REJECTED%' AND {eval_alias}.status != 'USER_DISMISSED'
            ORDER BY {eval_alias}.evaluated_at DESC
            '''
            params = user_param
        elif 'linkedin' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE (j.url LIKE '%linkedin.com%' OR j.url LIKE '%licdn%') AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'indeed' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE j.url LIKE '%indeed.%' AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'xing' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE j.url LIKE '%xing.com%' AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'bund' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE (j.url LIKE '%bund.de%' OR j.url LIKE '%interamt.de%') AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'ba' in raw_dataset or 'arbeitsagentur' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE j.url LIKE '%arbeitsagentur.de%' AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'personio' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE j.url LIKE '%personio%' AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'ashby' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE j.url LIKE '%ashbyhq%' AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'greenhouse' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE (j.url LIKE '%greenhouse.io%' OR j.url LIKE '%gh_jid%') AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        elif 'arbeitnow' in raw_dataset:
            q = base_select + f'''
            {eval_join_left}
            WHERE j.url LIKE '%arbeitnow%' AND COALESCE({eval_alias}.status, '') != 'USER_DISMISSED'
            ORDER BY COALESCE({eval_alias}.score, 0) DESC, j.id DESC
            '''
            params = user_param
        else:  # Default: ai_approved
            q = base_select + f'''
            {eval_join_inner}
            WHERE {eval_alias}.status LIKE 'APPROVED%' AND {eval_alias}.status != 'USER_DISMISSED'
            ORDER BY {eval_alias}.score DESC
            '''
            params = user_param

        df = pd.read_sql_query(q, conn, params=params if params else None)
        conn.close()
        df = clean_jobs_df(df)
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile")
def get_candidate_profile(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return verified candidate profile facts, verified projects, and skills taxonomy for current user."""
    try:
        user_id = current_user.get("id", 0)
        is_admin = current_user.get("role") == "admin"
        saved = get_user_profile(user_id) if user_id > 0 else None

        if saved:
            p = saved
        elif is_admin and user_id > 0:
            from src.core import config
            p = config.load_candidate_profile()
            if p:
                save_user_profile(user_id, p)
        else:
            # Blank starter template for guest or new SaaS user (Zero private Toyanath details)
            p = {
                "personal_info": {
                    "name": current_user.get("full_name", "") if user_id > 0 else "",
                    "email": current_user.get("email", "") if user_id > 0 else "",
                },
                "education": [],
                "experience": [],
                "skills": {},
                "languages": {},
                "projects": [],
                "experience_summary": "",
                "job_search_preferences": {},
            }

        # Parse structured work experience from experience_summary if present
        import re
        experiences = p.get("experience", [])
        raw_summary = p.get("experience_summary", "")
        if not experiences and raw_summary:
            experiences = []
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
            "user_id": user_id,
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


@router.put("/profile")
def update_candidate_profile(
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Save or update candidate profile facts for current user."""
    user_id = current_user.get("id", 1)
    success = save_user_profile(user_id, body)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save profile")
    return {"success": True, "user_id": user_id, "profile": body}


import tempfile
import threading

LEARNED_FIELDS_PATH = os.path.join("data", "learned_fields.json")
_LEARNED_FIELDS_LOCK = threading.Lock()


def _load_learned_fields() -> dict[str, str]:
    with _LEARNED_FIELDS_LOCK:
        if os.path.exists(LEARNED_FIELDS_PATH):
            try:
                with open(LEARNED_FIELDS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                logger.warning(f"Could not read learned fields from disk: {e}")
        return {}


def _save_learned_fields(fields: dict[str, str]) -> dict[str, str]:
    with _LEARNED_FIELDS_LOCK:
        target_dir = os.path.dirname(LEARNED_FIELDS_PATH) or "data"
        os.makedirs(target_dir, exist_ok=True)
        current = {}
        if os.path.exists(LEARNED_FIELDS_PATH):
            try:
                with open(LEARNED_FIELDS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        current = data
            except Exception:
                current = {}

        for k, v in fields.items():
            k_clean = str(k).strip().lower()
            v_clean = str(v).strip()
            if k_clean and v_clean:
                current[k_clean] = v_clean

        tmp_fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix="learned_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, LEARNED_FIELDS_PATH)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

        return current


@router.get("/profile/custom-fields")
def get_custom_fields(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return all saved and learned form fields for the current user."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"
    if not user_id or user_id <= 0:
        return {"fields": {}}
    if is_admin and LEARNED_FIELDS_PATH != os.path.join("data", "learned_fields.json"):
        return {"fields": _load_learned_fields()}
    db_fields = get_user_learned_fields(user_id)
    if not db_fields and is_admin:
        # Fallback to file for legacy local single-user mode
        disk_fields = _load_learned_fields()
        if disk_fields:
            save_user_learned_fields(user_id, disk_fields)
            return {"fields": disk_fields}
    return {"fields": db_fields}


@router.post("/profile/custom-fields")
def save_custom_fields(
    body: CustomFieldsRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Store or update newly learned form fields scoped to current user."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"
    if not user_id or user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required")
    if is_admin and LEARNED_FIELDS_PATH != os.path.join("data", "learned_fields.json"):
        updated = _save_learned_fields(body.fields)
        return {"success": True, "count": len(updated), "fields": updated}
    updated = save_user_learned_fields(user_id, body.fields)
    if is_admin:
        _save_learned_fields(body.fields)
    return {"success": True, "count": len(updated), "fields": updated}



