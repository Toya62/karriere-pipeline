"""CRM tracker endpoints: applications CRUD and tracker views."""

import os
import re
import sqlite3
import time

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from src.core.logger import get_logger
from src.dashboard.routers.auth import get_current_user
from src.db.database import get_db_connection, is_postgres
from src.dashboard.applications import autoresolve_cv_pdf, get_newest_cv_pdf
from src.dashboard.crm import (
    UNSET,
    clean_cell,
    load_tracker_df,
    upsert_tracker_row,
)
from src.dashboard.dismissals import add_to_dismissed
from src.dashboard.git_ops import git_sync_async
from src.dashboard.schemas import (
    ApplicationDeleteRequest,
    ApplicationPatchRequest,
    ApplicationSubmitRequest,
    ApplicationUpsertRequest,
    MessageResponse,
    SuccessResponse,
)
from src.dashboard.state import CACHE, CACHE_TTL_SECONDS, clear_data_caches

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["tracker"])

DB_PATH = os.path.join('data', 'karriere.db')

_EMAIL_MAP_CACHE = None


def _get_email_map():
    global _EMAIL_MAP_CACHE
    if _EMAIL_MAP_CACHE is not None:
        return _EMAIL_MAP_CACHE
    try:
        from src.generators.email import _get_jobs_df, extract_email
        jobs_df = _get_jobs_df()
        m = {}
        if jobs_df is not None and not jobs_df.empty:
            for _, r in jobs_df.iterrows():
                em = extract_email(str(r.get('job_url', ''))) or extract_email(str(r.get('description', '')))
                if em:
                    u = str(r.get('job_url', '')).strip()
                    c = re.sub(r'[^a-z0-9]', '', str(r.get('company', '')).lower())
                    if u:
                        m[u] = em
                    if c:
                        m[c] = em
        _EMAIL_MAP_CACHE = m
    except Exception as e:
        logger.warning(f"Failed to build email map cache: {e}")
        _EMAIL_MAP_CACHE = {}
    return _EMAIL_MAP_CACHE


@router.get("/tracker")
@router.get("/crm-data")
def get_tracker(current_user: dict = Depends(get_current_user)):
    """Return CRM tracker rows, newest application first, with contact emails."""
    try:
        user_id = current_user.get("id", 0)
        if not user_id or user_id <= 0:
            return []

        now = time.time()
        tracker_cache_key = f"tracker_{user_id}"
        if tracker_cache_key in CACHE and (now - CACHE[tracker_cache_key]["time"]) < CACHE_TTL_SECONDS:
            return CACHE[tracker_cache_key]["data"]

        df = load_tracker_df(user_id=user_id)
        if not df.empty:
            df = df.astype(object).where(pd.notnull(df), None)
            records = df.to_dict(orient='records')
            email_map = _get_email_map()
            from src.generators.email import extract_email
            for idx, rec in enumerate(records):
                rec['_csv_index'] = idx
                job_u = str(rec.get('job_url') or '').strip()
                comp_c = re.sub(r'[^a-z0-9]', '', str(rec.get('company') or '').lower())
                if job_u and ('@' in job_u or job_u.lower().startswith('mailto:')):
                    rec['email_contact'] = extract_email(job_u)
                elif job_u and job_u in email_map:
                    rec['email_contact'] = email_map[job_u]
                elif comp_c and comp_c in email_map:
                    rec['email_contact'] = email_map[comp_c]
                elif 'innogpt' in comp_c:
                    rec['email_contact'] = 'hello@innogpt.de'
        else:
            records = []

        records.sort(key=lambda x: (x.get("date_applied", "") or "", x.get("_csv_index", 0)), reverse=True)
        CACHE[tracker_cache_key] = {"data": records, "time": time.time()}
        return records
    except Exception as e:
        logger.error(f"  [tracker] Unhandled error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tracker/refresh", response_model=MessageResponse)
def refresh_tracker():
    """Clear the in-memory tracker/job caches."""
    try:
        clear_data_caches()
        logger.info("[refresh] Cleared in-memory cache")
        return {"success": True, "message": "Cache cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/applied-urls")
def applied_urls(current_user: dict = Depends(get_current_user)):
    """Return every job URL already present in the CRM tracker for the current user."""
    try:
        user_id = current_user.get("id", 0)
        if not user_id or user_id <= 0:
            return []
        urls = []
        df = load_tracker_df(user_id=user_id)
        if not df.empty and 'job_url' in df.columns:
            urls = df['job_url'].dropna().tolist()
        return urls
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_extra_documents() -> dict[str, str]:
    """Return dictionary of available credential documents for ATS form upload."""
    docs_dir = os.path.join("data", "documents")
    res = {}
    for key in ["master_urkunde", "job_references", "transcripts", "other_certificates"]:
        fpath = os.path.join(docs_dir, f"{key}.pdf")
        if os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
            res[key] = f"/api/documents/download/{key}.pdf"
    return res


import urllib.parse


def _canonical_job_url(raw_url: str) -> str:
    """Canonicalize job URL: strip tracking/analytics params but preserve identifying query parameters (e.g. gh_jid, id)."""
    if not raw_url:
        return ""
    try:
        p = urllib.parse.urlparse(raw_url.strip())
        netloc = p.netloc.lower()
        if netloc == "job-boards.greenhouse.io":
            netloc = "boards.greenhouse.io"
        elif "myworkdayjobs.com" in netloc:
            netloc = re.sub(r"\.wd\d+\.myworkdayjobs\.com$", ".myworkdayjobs.com", netloc)

        tracking_prefixes = ("utm_", "ref", "source", "trk", "tracking", "fbclid", "gclid", "urlhash")
        qs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        filtered_qs = [
            (k, v) for k, v in qs
            if not any(k.lower().startswith(pref) for pref in tracking_prefixes)
        ]
        filtered_qs.sort()
        new_query = urllib.parse.urlencode(filtered_qs)
        norm_path = p.path.rstrip("/")
        return urllib.parse.urlunparse((p.scheme.lower(), netloc, norm_path, "", new_query, ""))
    except Exception:
        return raw_url.strip().rstrip("/")


@router.get("/applications/lookup")
def lookup_application(url: str = Query(""), company: str = Query("")):
    """Find tailored application documents by job URL or company name for the browser extension."""
    target_url = url.strip()
    target_co = company.strip()
    extra_docs = _get_extra_documents()

    try:
        df = load_tracker_df()
        match = None
        if not df.empty:
            if target_url and 'job_url' in df.columns:
                canon_target = _canonical_job_url(target_url)
                for _, r in df.iterrows():
                    u = _canonical_job_url(str(r.get('job_url', '')))
                    if canon_target and u and canon_target == u:
                        match = r
                        break

                # If no exact canonical match, attempt job-id matching
                if match is None and canon_target:
                    target_id_m = re.search(r'(?:gh_jid=|/jobs?/|/job/)(\d+)', target_url)
                    if target_id_m:
                        target_jid = target_id_m.group(1)
                        for _, r in df.iterrows():
                            u_str = str(r.get('job_url', ''))
                            if target_jid in u_str:
                                match = r
                                break

            if match is None and target_co and 'company' in df.columns:
                co_lower = target_co.lower()
                co_matches = [
                    r for _, r in df.iterrows()
                    if co_lower == str(r.get('company', '')).strip().lower()
                ]
                if len(co_matches) == 1:
                    match = co_matches[0]

        if match is not None:
            cv_rel = str(match.get('cv_pdf_path') or '').lstrip('/')
            cover_rel = str(match.get('cover_pdf_path') or '').lstrip('/')
            cv_exists = bool(cv_rel and os.path.isfile(os.path.join(os.getcwd(), cv_rel)))
            cover_exists = bool(cover_rel and os.path.isfile(os.path.join(os.getcwd(), cover_rel)))
            cv_filename = os.path.basename(cv_rel) if cv_exists else ""
            cover_filename = os.path.basename(cover_rel) if cover_exists else ""
            cover_text = ""
            if cover_exists:
                try:
                    import pdfplumber
                    with pdfplumber.open(os.path.join(os.getcwd(), cover_rel)) as pdf:
                        cover_text = "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()
                except Exception:
                    pass
            return {
                "found": True,
                "company": str(match.get('company', '')),
                "position": str(match.get('position', '')),
                "job_url": str(match.get('job_url', '')),
                "status": str(match.get('status', 'Prepared')),
                "cv_path": f"/{cv_rel}" if cv_exists else "",
                "cover_path": f"/{cover_rel}" if cover_exists else "",
                "cv_filename": cv_filename,
                "cover_filename": cover_filename,
                "cover_text": cover_text,
                "extra_documents": extra_docs,
            }

        # Strict CRM Integrity: NEVER fallback to any master CV or unrelated company files.
        return {
            "found": False,
            "company": target_co,
            "position": "",
            "job_url": target_url,
            "status": "None",
            "cv_path": "",
            "cover_path": "",
            "cv_filename": "",
            "cover_filename": "",
            "extra_documents": extra_docs,
        }
    except Exception as e:
        logger.error(f"Error looking up application: {e}")
        return {
            "found": False,
            "error": str(e),
            "cv_path": "",
            "cover_path": "",
            "cv_filename": "cv_Toyanath_Pandey.pdf",
            "cover_filename": "cover_letter_Toyanath_Pandey.pdf",
            "extra_documents": extra_docs,
        }


@router.post("/applications")
def create_or_update_application(
    body: ApplicationUpsertRequest,
    current_user: dict = Depends(get_current_user),
):
    """Insert or update a CRM application row."""
    from src.core.entitlements import check_rate_limit, record_usage
    has_quota, quota_msg, quota_stats = check_rate_limit(current_user, "crm_jobs", increment=1)
    if not has_quota:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "tier_limit_reached",
                "tier": current_user.get("tier", "free"),
                "message": f"CRM capacity limit reached ({quota_stats['used']}/{quota_stats['limit']} jobs). Upgrade to PRO for unlimited job tracking.",
                "stats": quota_stats,
                "upgrade_url": "/upgrade",
            },
        )

    try:
        if not body.cv_pdf_path:
            resolved = autoresolve_cv_pdf(body.company, body.position)
            if resolved:
                body.cv_pdf_path = resolved

        notes_val = body.notes if "notes" in body.model_fields_set else UNSET
        upsert_tracker_row(
            company=body.company,
            position=body.position,
            job_url=body.job_url,
            cv_path=body.cv_pdf_path or UNSET,
            cover_path=body.cover_pdf_path or UNSET,
            notes=notes_val,
            date_applied=clean_cell(body.date_applied) or UNSET,
            user_id=current_user.get("id", 1),
        )
        record_usage(current_user.get("id", 0), "crm_jobs", 1)
        clear_data_caches()
        git_sync_async("feat: crm add/update application [auto]")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/applications")
@router.patch("/applications/notes")
def patch_application(body: ApplicationPatchRequest, current_user: dict = Depends(get_current_user)):
    """Update only the matched CRM row (notes, status, sent fields, follow up)."""
    try:
        user_id = current_user.get("id") or 1
        notes_val = body.notes if "notes" in body.model_fields_set else UNSET
        status_val = body.status if "status" in body.model_fields_set else UNSET
        sent_at_val = body.sent_at if "sent_at" in body.model_fields_set else UNSET
        sent_method_val = body.sent_method if "sent_method" in body.model_fields_set else UNSET
        sent_to_val = body.sent_to if "sent_to" in body.model_fields_set else UNSET
        follow_up_val = body.follow_up_at if "follow_up_at" in body.model_fields_set else UNSET

        updated = upsert_tracker_row(
            company=body.company or "",
            position=body.position or "",
            job_url=body.job_url or "",
            notes=notes_val,
            status=status_val,
            sent_at=sent_at_val,
            sent_method=sent_method_val,
            sent_to=sent_to_val,
            follow_up_at=follow_up_val,
            create=False,
            user_id=user_id,
        )
        if updated:
            clear_data_caches()
            git_sync_async("feat: crm update application status [auto]")
            return {"success": True}
        return JSONResponse(
            status_code=404,
            content={"error": "Application record not found.", "job_url": body.job_url, "company": body.company},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/applications/submit")
def submit_application(body: ApplicationSubmitRequest, current_user: dict = Depends(get_current_user)):
    """Submit an application: moves status Prepared -> Applied, records sent_at, logs email if present."""
    from datetime import datetime, timedelta
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    follow_up_str = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    user_id = current_user.get("id") or 1

    try:
        updated = upsert_tracker_row(
            company=body.company or "",
            position=body.position or "",
            job_url=body.job_url or "",
            status="Applied",
            date_applied=now_str[:10],
            sent_at=now_str,
            sent_method=body.sent_method or "email",
            sent_to=body.sent_to,
            follow_up_at=follow_up_str,
            notes=body.notes or UNSET,
            create=False,
            user_id=user_id,
        )
        if not updated:
            return JSONResponse(status_code=404, content={"error": "Application record not found"})

        # Record email log if body and subject are present
        if body.sent_to and (body.body or body.subject):
            from src.db.database import get_db_connection, is_postgres
            db_p = "data/karriere.db"
            if is_postgres() or os.path.exists(db_p):
                with get_db_connection(db_p) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT a.id FROM applications a
                        JOIN jobs j ON a.job_id = j.id
                        WHERE (j.url = ? OR (j.company = ? AND j.title = ?)) AND (a.user_id = ? OR a.user_id IS NULL)
                        LIMIT 1
                        """,
                        (body.job_url or "", body.company or "", body.position or "", user_id)
                    )
                    r = cur.fetchone()
                    if r:
                        app_id = r[0]
                        cur.execute(
                            """
                            INSERT INTO sent_emails (application_id, recipient, subject, body, sent_at, status)
                            VALUES (?, ?, ?, ?, ?, 'SENT')
                            """,
                            (app_id, body.sent_to, body.subject or "", body.body or "", now_str)
                        )
                        conn.commit()

        clear_data_caches()
        git_sync_async("feat: crm submit application [auto]")
        return {
            "success": True,
            "status": "Applied",
            "sent_at": now_str,
            "follow_up_at": follow_up_str
        }
    except Exception as e:
        logger.error(f"Failed submitting application: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/applications")
def delete_application(
    payload: ApplicationDeleteRequest | None = None,
    keep_job: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Delete an application's files and CRM rows.

    By default the job is also recorded as dismissed (legacy behaviour). With
    ``keep_job=true`` only the CRM row and its files are removed: the ``jobs``
    row is untouched and nothing is dismissed, so the job stays in Job Finder.
    """
    try:
        user_id = current_user.get("id") or 1
        cv_pdf_path = getattr(payload, 'cv_pdf_path', None)
        company = getattr(payload, 'company', None)
        position = getattr(payload, 'position', None)
        job_url = getattr(payload, 'job_url', None)

        if cv_pdf_path and cv_pdf_path not in ("N/A", "", "null"):
            cv_pdf_clean = cv_pdf_path.replace("\\", "/").strip()
            if not (".." in cv_pdf_clean or not cv_pdf_clean.startswith("applications/")):
                related_files = [
                    cv_pdf_clean,
                    cv_pdf_clean.replace("_cv.pdf", "_cover.pdf"),
                    cv_pdf_clean.replace("_cv.pdf", ".meta.json"),
                    cv_pdf_clean.replace("_cv.pdf", "_cv.tex"),
                    cv_pdf_clean.replace("_cv.pdf", "_cover.tex"),
                ]
                for rel_file in related_files:
                    if os.path.exists(rel_file):
                        try:
                            os.remove(rel_file)
                        except Exception as del_err:
                            logger.error(f"Failed to delete {rel_file}: {del_err}")

        if is_postgres() or os.path.exists(DB_PATH):
            try:
                conn = get_db_connection(DB_PATH)
                cur = conn.cursor()
                if cv_pdf_path and str(cv_pdf_path).strip() not in ("N/A", "", "null"):
                    clean_cv = str(cv_pdf_path).replace("\\", "/").strip().lstrip('/')
                    cur.execute(
                        "DELETE FROM applications WHERE ltrim(replace(cv_pdf_path, '\\', '/'), '/') = ? AND (user_id = ? OR user_id IS NULL)",
                        (clean_cv, user_id),
                    )
                if company and position:
                    cur.execute(
                        "DELETE FROM applications WHERE (user_id = ? OR user_id IS NULL) AND job_id IN "
                        "(SELECT id FROM jobs WHERE company = ? AND title = ?)",
                        (user_id, str(company).strip(), str(position).strip()),
                    )
                elif job_url and str(job_url).strip() not in ("N/A", "", "null"):
                    cur.execute(
                        "DELETE FROM applications WHERE (user_id = ? OR user_id IS NULL) AND job_id IN (SELECT id FROM jobs WHERE url = ?)",
                        (user_id, str(job_url).strip()),
                    )
                conn.commit()
                conn.close()
            except Exception as dbe:
                logger.error(f"Failed deleting application from DB: {dbe}")

        if not keep_job:
            add_to_dismissed(job_url=job_url, company=company, position=position)
        clear_data_caches()
        git_sync_async("feat: crm delete application [auto]")
        return {"success": True}
    except Exception as e:
        logger.error(f"Delete application error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/funnel-stats")
def get_funnel_stats(current_user: dict = Depends(get_current_user)):
    """Return operational command-center metrics, action inbox queues, and pipeline intelligence."""
    try:
        from collections import defaultdict, Counter
        from datetime import datetime
        from urllib.parse import urlparse

        user_id = current_user.get("id", 0)
        if not user_id or user_id <= 0:
            return {
                "counts": {
                    "total_jobs": 0,
                    "pending_evaluations": 0,
                    "total_evaluated": 0,
                    "total_approved": 0,
                    "total_applied": 0,
                    "ready_to_submit_count": 0,
                    "uncompiled_approved_count": 0,
                },
                "ready_to_submit": [],
                "ready_to_generate": [],
                "portal_harvest": {},
                "ai_rejections": {},
                "archetype_distribution": {},
                "stages": {
                    "draft": 0,
                    "applied": 0,
                    "screening": 0,
                    "interview": 0,
                    "offer": 0,
                    "rejected": 0,
                    "total": 0,
                },
                "conversions": {
                    "applied_to_interview": 0.0,
                    "interview_to_offer": 0.0,
                },
                "weekly_activity": [],
                "top_recommendations": [],
            }

        df = load_tracker_df(user_id=user_id)
        stages = {
            "draft": 0,
            "applied": 0,
            "screening": 0,
            "interview": 0,
            "offer": 0,
            "rejected": 0,
            "total": 0,
        }
        ready_to_submit = []
        if not df.empty:
            stages["total"] = len(df)
            for _, r in df.iterrows():
                st = str(r.get("status", "")).strip().lower()
                if st in ("prepared", "draft", "not applied"):
                    stages["draft"] += 1
                elif st in ("applied", "sent"):
                    stages["applied"] += 1
                elif st in ("screening", "assessment"):
                    stages["screening"] += 1
                elif st in ("interview", "technical interview"):
                    stages["interview"] += 1
                elif st in ("offer", "accepted"):
                    stages["offer"] += 1
                elif st in ("rejected", "declined", "user_dismissed", "ghosted"):
                    stages["rejected"] += 1
                else:
                    stages["draft"] += 1

            # Extract prepared drafts waiting to be submitted
            draft_df = df[df["status"].str.lower().isin(["prepared", "draft", "not applied"])].copy()
            for _, r in draft_df.iterrows():
                ready_to_submit.append({
                    "company": str(r.get("company", "") or ""),
                    "position": str(r.get("position", "") or ""),
                    "status": str(r.get("status", "prepared") or "prepared"),
                    "date_applied": str(r.get("date_applied", "") or ""),
                    "cv_pdf_path": str(r.get("cv_pdf_path", "") or ""),
                    "cover_pdf_path": str(r.get("cover_pdf_path", "") or ""),
                    "job_url": str(r.get("job_url", "") or ""),
                    "notes": str(r.get("notes", "") or ""),
                })

        active_funnel = stages["applied"] + stages["screening"] + stages["interview"] + stages["offer"] + stages["rejected"]
        applied_to_interview = round(((stages["interview"] + stages["offer"]) / max(1, active_funnel)) * 100, 1)
        interview_to_offer = round((stages["offer"] / max(1, stages["interview"] + stages["offer"])) * 100, 1)

        weekly = defaultdict(lambda: {"applied": 0, "prepared": 0})
        if not df.empty:
            for _, r in df.iterrows():
                dt_str = str(r.get("date_applied") or r.get("applied_at") or "").strip()
                if dt_str and len(dt_str) >= 10:
                    try:
                        d = datetime.strptime(dt_str[:10], "%Y-%m-%d")
                        w_key = f"W{d.isocalendar()[1]} ({d.strftime('%b')})"
                        st = str(r.get("status", "")).strip().lower()
                        if st in ("applied", "sent", "interview", "offer"):
                            weekly[w_key]["applied"] += 1
                        else:
                            weekly[w_key]["prepared"] += 1
                    except Exception:
                        pass

        # DB Engine Metrics & Action Queue (Scoped to user_id)
        is_admin = current_user.get("role") == "admin"
        total_jobs = 0
        pending_evaluations = 0
        total_evaluated = 0
        total_approved = 0
        portal_harvest = {}
        ai_rejections = {}
        archetype_distribution = {}
        ready_to_generate = []
        uncompiled_count = 0

        try:
            conn = get_db_connection(DB_PATH)
            cur = conn.cursor()

            # Check if user_jobs table exists
            has_user_jobs = False
            try:
                cur.execute("SELECT 1 FROM user_jobs LIMIT 1")
                has_user_jobs = True
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass

            # 1. Total jobs: global harvest for admin, strictly own user_jobs for candidates
            if is_admin:
                cur.execute("SELECT COUNT(*) FROM jobs")
                row = cur.fetchone()
                total_jobs = row[0] if row else 0
            else:
                if has_user_jobs:
                    cur.execute("SELECT COUNT(*) FROM user_jobs WHERE user_id = ?", (user_id,))
                    row = cur.fetchone()
                    total_jobs = row[0] if row else 0
                else:
                    total_jobs = 0

            if has_user_jobs:
                # 2. Pending evaluations: global un-evaluated for admin, 0 for new candidate accounts
                if is_admin:
                    cur.execute("SELECT COUNT(*) FROM jobs j LEFT JOIN user_jobs uj ON j.id = uj.job_id AND uj.user_id = ? WHERE uj.id IS NULL", (user_id,))
                    row = cur.fetchone()
                    pending_evaluations = row[0] if row else 0
                else:
                    pending_evaluations = 0

                # 3. Total evaluated & approved for user
                cur.execute("SELECT COUNT(*) FROM user_jobs WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
                total_evaluated = row[0] if row else 0

                cur.execute("SELECT COUNT(*) FROM user_jobs WHERE user_id = ? AND status LIKE 'APPROVED%'", (user_id,))
                row = cur.fetchone()
                total_approved = row[0] if row else 0

                # 4. AI Rejections breakdown for user
                cur.execute("SELECT status, COUNT(*) FROM user_jobs WHERE user_id = ? AND status LIKE 'REJECTED%' GROUP BY status", (user_id,))
                rej_raw = dict(cur.fetchall())

                # 5. Archetype distribution for approved
                cur.execute("""
                    SELECT LOWER(archetype) AS arch, COUNT(*) 
                    FROM user_jobs 
                    WHERE user_id = ? AND status LIKE 'APPROVED%' AND archetype IS NOT NULL AND archetype != '' 
                    GROUP BY LOWER(archetype)
                    ORDER BY COUNT(*) DESC
                """, (user_id,))
                archetype_distribution = dict(cur.fetchall())

                # 6. Uncompiled Approved Jobs for user
                cur.execute("""
                    SELECT COUNT(*) FROM jobs j
                    JOIN user_jobs uj ON j.id = uj.job_id AND uj.user_id = ?
                    LEFT JOIN applications a ON j.id = a.job_id AND a.user_id = ?
                    WHERE uj.status LIKE 'APPROVED%' AND a.id IS NULL
                """, (user_id, user_id))
                row = cur.fetchone()
                uncompiled_count = row[0] if row else 0

                cur.execute("""
                    SELECT j.id, j.company, j.title, j.location, uj.score, uj.archetype, uj.matched_skills, uj.gaps, j.url, j.scraped_at
                    FROM jobs j
                    JOIN user_jobs uj ON j.id = uj.job_id AND uj.user_id = ?
                    LEFT JOIN applications a ON j.id = a.job_id AND a.user_id = ?
                    WHERE uj.status LIKE 'APPROVED%' AND a.id IS NULL
                    ORDER BY uj.score DESC, j.id DESC
                    LIMIT 30
                """, (user_id, user_id))
                for row in cur.fetchall():
                    ready_to_generate.append({
                        "id": row[0],
                        "company": row[1],
                        "title": row[2],
                        "location": row[3],
                        "score": row[4],
                        "archetype": row[5],
                        "matched_skills": row[6],
                        "gaps": row[7],
                        "url": row[8],
                        "scraped_at": row[9],
                    })
            else:
                # Fallback to evaluations if legacy DB
                cur.execute("SELECT COUNT(*) FROM jobs j LEFT JOIN evaluations e ON j.id = e.job_id WHERE e.id IS NULL")
                row = cur.fetchone()
                pending_evaluations = row[0] if row else 0

                cur.execute("SELECT COUNT(*) FROM evaluations")
                row = cur.fetchone()
                total_evaluated = row[0] if row else 0

                cur.execute("SELECT COUNT(*) FROM evaluations WHERE status LIKE 'APPROVED%'")
                row = cur.fetchone()
                total_approved = row[0] if row else 0

                cur.execute("SELECT status, COUNT(*) FROM evaluations WHERE status LIKE 'REJECTED%' GROUP BY status")
                rej_raw = dict(cur.fetchall())

                cur.execute("""
                    SELECT LOWER(archetype) AS arch, COUNT(*) 
                    FROM evaluations 
                    WHERE status LIKE 'APPROVED%' AND archetype IS NOT NULL AND archetype != '' 
                    GROUP BY LOWER(archetype)
                    ORDER BY COUNT(*) DESC
                """)
                archetype_distribution = dict(cur.fetchall())

            # Portal distribution from URLs: all jobs for admin, strictly user's jobs for candidates
            if is_admin:
                cur.execute("SELECT url FROM jobs WHERE url IS NOT NULL")
            else:
                if has_user_jobs:
                    cur.execute("""
                        SELECT j.url FROM jobs j
                        JOIN user_jobs uj ON j.id = uj.job_id
                        WHERE uj.user_id = ? AND j.url IS NOT NULL
                    """, (user_id,))
                else:
                    cur.execute("SELECT url FROM jobs WHERE 1=0")
            domains = [urlparse(r[0]).netloc.replace("www.", "") for r in cur.fetchall() if r[0]]
            portal_map = {
                "linkedin.com": "LinkedIn",
                "arbeitsagentur.de": "Bundesagentur",
                "de.indeed.com": "Indeed",
                "indeed.com": "Indeed",
                "xing.com": "Xing",
                "arbeitnow.com": "Arbeitnow",
                "arbeitnow.nl": "Arbeitnow",
                "service.bund.de": "Bund.de",
                "stepstone.de": "StepStone",
            }
            p_counts = Counter()
            for d in domains:
                p_counts[portal_map.get(d, "Direct / Company")] += 1
            portal_harvest = dict(p_counts.most_common(7))

            rej_map = {
                "REJECTED_LANGUAGE": "German B2/C1 Gate",
                "REJECTED_SENIORITY_EXP": "Seniority / Niche Gate",
                "REJECTED_TECH_MISMATCH": "Central Tech Mismatch",
                "REJECTED_STAFFING_AGENCY": "Staffing Agency",
                "REJECTED_NATIVE_EXCLUSIVE": "Native / Gov Security Gate",
                "REJECTED_ROLE_MISMATCH": "Role Mismatch",
            }
            ai_rejections = {rej_map.get(k, k): v for k, v in rej_raw.items()}

            conn.close()
        except Exception as e_engine:
            logger.warning(f"Engine stats calculation warning: {e_engine}")

        return {
            "counts": {
                "total_jobs": total_jobs,
                "pending_evaluations": pending_evaluations,
                "total_evaluated": total_evaluated,
                "total_approved": total_approved,
                "total_applied": stages["applied"],
                "ready_to_submit_count": len(ready_to_submit),
                "uncompiled_approved_count": uncompiled_count,
            },
            "ready_to_submit": ready_to_submit[:30],
            "ready_to_generate": ready_to_generate,
            "portal_harvest": portal_harvest,
            "ai_rejections": ai_rejections,
            "archetype_distribution": archetype_distribution,
            # Backwards compatibility
            "stages": stages,
            "conversions": {
                "applied_to_interview": applied_to_interview,
                "interview_to_offer": interview_to_offer,
            },
            "weekly_activity": [{"week": k, **v} for k, v in list(weekly.items())[-6:]],
            "top_recommendations": ready_to_generate[:5],
        }
    except Exception as e:
        logger.error(f"Failed to calculate funnel stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
