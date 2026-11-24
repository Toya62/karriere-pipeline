"""Application and email generation endpoints."""

import json
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from src.core.entitlements import check_rate_limit, record_usage
from src.core.logger import get_logger
from src.dashboard.applications import (
    classify_generation_error,
    launch_application_generation,
    register_application_in_crm,
)
from src.dashboard.routers.auth import get_current_user, require_authenticated_user
from src.dashboard.schemas import (
    AIFormAutofillRequest,
    AIFormAutofillResponse,
    AnswerFormQuestionRequest,
    AutoFillRequest,
    GenerateApplicationRequest,
    GenerateEmailRequest,
)
from src.dashboard.state import APP_GEN_STATUS, set_gen_status

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["generation"])


@router.get("/generate-application/status")
def generation_status(
    task_key: str = Query(""),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    if not task_key:
        return JSONResponse(status_code=400, content={"error": "Missing task_key parameter"})
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin" or user_id <= 1

    from src.dashboard.applications import get_generation_queue_stats, get_task_queue_position
    if task_key in ("all", "*"):
        tasks = {}
        for k, v in list(APP_GEN_STATUS.items()):
            if isinstance(v, dict):
                task_user = v.get("user_id", 1)
                if is_admin or task_user == user_id:
                    task_item = dict(v)
                    if task_item.get("status") == "queued":
                        live_pos = get_task_queue_position(k)
                        if live_pos is not None:
                            task_item["queue_position"] = live_pos
                    tasks[k] = task_item
        return {
            "status": "ok",
            "queue_stats": get_generation_queue_stats(),
            "tasks": tasks
        }

    status = APP_GEN_STATUS.get(task_key)
    if not status:
        return {"status": "not_found", "message": "No generation task found"}

    task_user = status.get("user_id", 1) if isinstance(status, dict) else 1
    if not is_admin and task_user != user_id:
        return {"status": "not_found", "message": "No generation task found"}

    if isinstance(status, dict) and status.get("status") == "queued":
        live_pos = get_task_queue_position(task_key)
        if live_pos == 0:
            status = dict(status, status="running", queue_position=0)
        elif live_pos is not None:
            status = dict(status, queue_position=live_pos)

    return status


@router.get("/generate-application/active")
def get_active_generations(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return all currently queued, running, or recently completed generation tasks with live positions."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin" or user_id <= 1
    from src.dashboard.applications import get_generation_queue_stats, get_task_queue_position
    tasks = {}
    for k, v in list(APP_GEN_STATUS.items()):
        if isinstance(v, dict):
            task_user = v.get("user_id", 1)
            if is_admin or task_user == user_id:
                task_item = dict(v)
                if task_item.get("status") == "queued":
                    live_pos = get_task_queue_position(k)
                    if live_pos == 0:
                        task_item["status"] = "running"
                        task_item["queue_position"] = 0
                    elif live_pos is not None:
                        task_item["queue_position"] = live_pos
                tasks[k] = task_item
    return {
        "queue_stats": get_generation_queue_stats(),
        "tasks": tasks
    }


@router.post("/generate-email")
def generate_email(
    body: GenerateEmailRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Draft an application email for a job."""
    has_quota, quota_msg, quota_stats = check_rate_limit(current_user, "form_copilot", increment=1)
    if not has_quota:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "tier_limit_reached",
                "tier": current_user.get("tier", "free"),
                "message": quota_msg,
                "stats": quota_stats,
                "upgrade_url": "/upgrade",
            },
        )

    user_id = int(current_user.get("id", 1) or 1)

    try:
        from src.generators.email import generate_application_email
        from src.db.database import get_user_profile

        candidate_profile = None
        if user_id > 1:
            candidate_profile = get_user_profile(user_id)

        result = generate_application_email(
            company=body.company,
            position=body.position,
            description=body.description,
            job_url=body.job_url,
            explicit_email=body.email,
            user_id=user_id,
            candidate_profile=candidate_profile,
        )
        record_usage(current_user.get("id", 0), "form_copilot", 1)
        return result
    except Exception as e:
        logger.error(f"Error in /api/generate-email: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/answer-form-question")
def answer_form_question(
    body: AnswerFormQuestionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Answer an application form question using Gemini grounded in verified candidate profile."""
    question = (body.question or "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "Question cannot be empty."})

    has_quota, quota_msg, quota_stats = check_rate_limit(current_user, "form_copilot", increment=1)
    if not has_quota:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "tier_limit_reached",
                "tier": current_user.get("tier", "free"),
                "message": quota_msg,
                "stats": quota_stats,
                "upgrade_url": "/upgrade",
            },
        )

    try:
        from src.generators.form_copilot import generate_form_answer
        from src.db.database import get_user_profile

        user_id = int(current_user.get("id", 1) or 1)
        cand_prof = get_user_profile(user_id) if user_id > 0 else None
        if not cand_prof and (current_user.get("role") == "admin" or user_id <= 1):
            from src.core import config
            cand_prof = config.load_candidate_profile()
        cand_name = None
        if isinstance(cand_prof, dict):
            cand_name = cand_prof.get("personal_info", {}).get("name")

        result = generate_form_answer(
            question=question,
            company=body.company,
            position=body.position,
            description=body.description,
            language=body.language,
            candidate_profile=cand_prof,
            candidate_name=cand_name,
            user_id=user_id,
        )
        if not result.get("success"):
            return JSONResponse(status_code=500, content={"error": result.get("error", "Failed to generate answer")})
        record_usage(current_user.get("id", 0), "form_copilot", 1)
        return result
    except Exception as e:
        logger.error(f"Error in /api/answer-form-question: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/ai-form-autofill")
def ai_form_autofill(
    body: AIFormAutofillRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
):
    """Resolve form fields semantically using Gemini grounded in verified profile facts."""
    fields = body.fields or []
    if not fields:
        return {
            "success": True,
            "resolutions": [],
            "fields_count": 0,
            "resolved_count": 0,
            "error": None,
        }

    has_quota, quota_msg, quota_stats = check_rate_limit(current_user, "form_copilot", increment=1)
    if not has_quota:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "tier_limit_reached",
                "tier": current_user.get("tier", "free"),
                "message": quota_msg,
                "stats": quota_stats,
                "upgrade_url": "/upgrade",
            },
        )

    try:
        from src.ai.form_resolver import resolve_form_fields
        from src.db.database import get_user_profile

        user_id = int(current_user.get("id", 1) or 1)
        cand_prof = get_user_profile(user_id) if user_id > 0 else None
        if not cand_prof and (current_user.get("role") == "admin" or user_id <= 1):
            from src.core import config
            cand_prof = config.load_candidate_profile()
        cand_name = None
        if isinstance(cand_prof, dict):
            cand_name = cand_prof.get("personal_info", {}).get("name")

        job_ctx = {
            "url": body.url,
            "company": body.company,
            "position": body.position,
            "description": body.description,
        }

        result = resolve_form_fields(
            fields=fields,
            job_context=job_ctx,
            candidate_profile=cand_prof,
            candidate_name=cand_name,
            user_id=user_id,
        )

        if not result.get("success"):
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": result.get("error", "Failed to resolve fields")},
            )

        record_usage(current_user.get("id", 0), "form_copilot", 1)
        return result
    except Exception as e:
        logger.error(f"Error in /api/ai-form-autofill: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@router.post("/generate-application")
def generate_application(
    body: GenerateApplicationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Generate a tailored ATS application, or report an existing task."""
    company = (body.company or "").strip()
    position = (body.position or "").strip()
    description = (body.description or "").strip()
    job_url = (body.job_url or "").strip()
    location = (body.location or "").strip()
    language = (body.language or "").strip() or None

    if not company or not position:
        return JSONResponse(status_code=400, content={"error": "Missing required fields: company and position"})

    if not description or len(description) < 50:
        return JSONResponse(status_code=400, content={
            "error": "Job description is too short or missing. A full description is needed for ATS keyword optimization."
        })

    has_quota, quota_msg, quota_stats = check_rate_limit(current_user, "applications", increment=1)
    if not has_quota:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "tier_limit_reached",
                "tier": current_user.get("tier", "free"),
                "message": quota_msg,
                "stats": quota_stats,
                "upgrade_url": "/upgrade",
            },
        )

    try:
        from src.generators.application import _slugify

        today = datetime.now().strftime("%Y-%m-%d")
        comp_slug = _slugify(company, max_len=20)
        pos_slug = _slugify(position, max_len=22)
        base_name = f"{comp_slug}_{pos_slug}"
        if len(base_name) > 42:
            base_name = base_name[:42].rstrip('-')
        user_id = int(current_user.get("id", 1) or 1)
        task_key = f"u{user_id}_{base_name}" if user_id > 1 else base_name
        candidate_profile = None
        if user_id > 1:
            from src.db.database import get_user_profile
            candidate_profile = get_user_profile(user_id)
            existing_cv = os.path.join('applications', f"user_{user_id}", today, f"{base_name}_cv.pdf")
            existing_meta = os.path.join('applications', f"user_{user_id}", today, f"{base_name}.meta.json")
        else:
            existing_cv = os.path.join('applications', today, f"{base_name}_cv.pdf")
            existing_meta = os.path.join('applications', today, f"{base_name}.meta.json")
        if os.path.exists(existing_cv):
            cover_path = existing_cv.replace('_cv.pdf', '_cover.pdf')
            cv_rel = existing_cv.replace('\\', '/')
            cover_rel = cover_path.replace('\\', '/') if os.path.exists(cover_path) else ""
            meta_rel = existing_meta.replace('\\', '/') if os.path.exists(existing_meta) else ""
            notes = "ATS-tailored package (existing)."
            try:
                if meta_rel and os.path.exists(existing_meta):
                    with open(existing_meta, 'r', encoding='utf-8') as mf:
                        meta_data = json.load(mf)
                    kws = meta_data.get('ats_keywords') or []
                    if kws:
                        notes = "ATS-tailored. Keywords: " + ", ".join(kws[:6])
                    notes += f" Meta: {meta_rel}"
            except Exception:
                pass
            # Ensure an already-generated package is present in the CRM.
            register_application_in_crm(company, position, job_url, cv_rel, cover_rel, notes, user_id=user_id)
            return {
                "success": True,
                "status": "already_exists",
                "task_key": task_key,
                "message": f"Application for {company} already exists for today.",
                "cv_path": cv_rel,
                "cover_path": cover_rel,
                "meta_path": meta_rel,
            }

        if task_key in APP_GEN_STATUS and APP_GEN_STATUS[task_key].get("status") in ("running", "queued"):
            st = APP_GEN_STATUS[task_key].get("status")
            return {
                "success": True,
                "status": st,
                "task_key": task_key,
                "queue_position": APP_GEN_STATUS[task_key].get("queue_position", 1),
                "message": APP_GEN_STATUS[task_key].get("message", "Generation already in progress or queued..."),
            }

        q_info = launch_application_generation(
            company=company,
            position=position,
            description=description,
            job_url=job_url,
            location=location,
            language=language,
            task_key=task_key,
            user_id=user_id,
            candidate_profile=candidate_profile,
        )
        record_usage(current_user.get("id", 0), "applications", 1)

        is_queued = q_info.get("queued", False)
        status_str = "queued" if is_queued else "generating"
        pos = q_info.get("queue_position", 1)
        msg = (
            f"Application for {company} queued (position #{pos})..."
            if is_queued
            else f"Generating ATS-tailored application for {company}..."
        )

        return JSONResponse(status_code=202, content={
            "success": True,
            "status": status_str,
            "task_key": task_key,
            "queue_position": pos,
            "message": msg,
        })
    except Exception as e:
        logger.error(f"Error in /api/generate-application: {e}")
        # Bug #1: a real error status + machine-readable reason instead of a
        # bare message, so the frontend can tell the user what happened.
        return JSONResponse(status_code=500, content={
            "error": str(e),
            "reason": classify_generation_error(str(e)),
        })


import ipaddress
import urllib.parse


def _validate_safe_job_url(raw_url: str) -> str:
    """Validate that job_url is http/https and does not target internal/private network addresses."""
    if not raw_url or not isinstance(raw_url, str) or not raw_url.strip():
        raise HTTPException(status_code=400, detail="Missing job_url")
    p = urllib.parse.urlparse(raw_url.strip())
    if p.scheme.lower() not in ("http", "https") or not p.netloc:
        raise HTTPException(status_code=400, detail="job_url must be a valid http or https URL")

    host = p.netloc.split(":")[0].strip("[]").lower()
    if host in ("localhost", "0.0.0.0", "127.0.0.1", "169.254.169.254"):
        raise HTTPException(status_code=400, detail="Targeting loopback or metadata addresses is not allowed")

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise HTTPException(status_code=400, detail="Targeting private network addresses is not allowed")
    except ValueError:
        pass

    return raw_url.strip()


def _validate_safe_pdf_path(path_str: str | None) -> str | None:
    """Validate and contain PDF path within approved application PDF directories."""
    if not path_str:
        return None
    raw = path_str.strip().lstrip("/")
    abs_path = os.path.abspath(raw if os.path.isabs(path_str) else os.path.join(os.getcwd(), raw))

    if not abs_path.lower().endswith(".pdf") or not os.path.isfile(abs_path):
        raise HTTPException(status_code=400, detail=f"File not found or not a PDF: {path_str}")

    allowed_dirs = [
        os.path.abspath("applications"),
        os.path.abspath(os.path.join("data", "documents")),
    ]
    if not any(abs_path.startswith(d) for d in allowed_dirs):
        raise HTTPException(status_code=400, detail=f"Path outside approved document directories: {path_str}")

    return abs_path


@router.post("/applications/auto-fill")
async def auto_fill_application(
    body: AutoFillRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Auto-fills application form using Playwright with CV and Cover letter."""
    job_url = _validate_safe_job_url(body.job_url or "")

    cv_path = _validate_safe_pdf_path((body.cv_path or "").strip() or None)
    cover_path = _validate_safe_pdf_path((body.cover_path or "").strip() or None)
    company = (body.company or "").strip()
    position = (body.position or "").strip()

    # If paths are not provided or relative, resolve them
    user_id = int(current_user.get("id", 1) or 1)
    from src.dashboard.applications import autoresolve_cv_pdf
    if not cv_path and company:
        resolved = autoresolve_cv_pdf(company, position, user_id=user_id)
        if resolved:
            cv_path = _validate_safe_pdf_path(resolved)
            if not cover_path:
                cand_cover = resolved.replace("_cv.pdf", "_cover.pdf")
                if os.path.exists(cand_cover):
                    cover_path = _validate_safe_pdf_path(cand_cover)

    # In GUI environments (Mac OS), launch headed so user can review visually.
    # In headless servers, actual_headed falls back to False safely in ATSFormFiller.
    headed = body.headed if body.headed is not None else True

    try:
        from src.automation.form_filler import ATSFormFiller
        from src.db.database import get_user_profile

        user_id = int(current_user.get("id", 1) or 1)
        candidate = None
        if user_id > 1:
            candidate = get_user_profile(user_id)

        filler = ATSFormFiller(candidate=candidate)
        result = await filler.fill_application(
            job_url=job_url,
            cv_path=cv_path,
            cover_path=cover_path,
            headed=headed,
            auto_submit=False,
            wait_for_user=False,  # Never block on stdin in API context
        )

        return {
            "success": True,
            "platform": result.get("platform", "generic"),
            "filled_fields": result.get("filled_fields", []),
            "attached_files": result.get("attached_files", []),
            "screenshot_base64": result.get("screenshot_base64"),
            "message": f"Auto-filled {len(result.get('filled_fields', []))} fields and attached {len(result.get('attached_files', []))} files on {result.get('platform', 'generic').upper()}.",
        }
    except Exception as e:
        logger.error(f"Error in /api/applications/auto-fill: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

