"""Application and email generation endpoints."""

import json
import os
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.core.logger import get_logger
from src.dashboard.applications import (
    launch_application_generation,
    register_application_in_crm,
)
from src.dashboard.schemas import (
    AnswerFormQuestionRequest,
    GenerateApplicationRequest,
    GenerateEmailRequest,
)
from src.dashboard.state import APP_GEN_STATUS, set_gen_status

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["generation"])


@router.get("/generate-application/status")
def generation_status(task_key: str = Query("")):
    if not task_key:
        return JSONResponse(status_code=400, content={"error": "Missing task_key parameter"})
    from src.dashboard.applications import get_generation_queue_stats, get_task_queue_position
    if task_key in ("all", "*"):
        tasks = dict(APP_GEN_STATUS)
        for k, v in list(tasks.items()):
            if isinstance(v, dict) and v.get("status") == "queued":
                live_pos = get_task_queue_position(k)
                if live_pos is not None:
                    tasks[k] = dict(v, queue_position=live_pos)
        return {
            "status": "ok",
            "queue_stats": get_generation_queue_stats(),
            "tasks": tasks
        }

    status = APP_GEN_STATUS.get(task_key)
    if not status:
        return {"status": "not_found", "message": "No generation task found"}

    if isinstance(status, dict) and status.get("status") == "queued":
        live_pos = get_task_queue_position(task_key)
        if live_pos == 0:
            status = dict(status, status="running", queue_position=0)
        elif live_pos is not None:
            status = dict(status, queue_position=live_pos)

    return status


@router.get("/generate-application/active")
def get_active_generations():
    """Return all currently queued, running, or recently completed generation tasks with live positions."""
    from src.dashboard.applications import get_generation_queue_stats, get_task_queue_position
    tasks = dict(APP_GEN_STATUS)
    for k, v in list(tasks.items()):
        if isinstance(v, dict) and v.get("status") == "queued":
            live_pos = get_task_queue_position(k)
            if live_pos == 0:
                tasks[k] = dict(v, status="running", queue_position=0)
            elif live_pos is not None:
                tasks[k] = dict(v, queue_position=live_pos)
    return {
        "queue_stats": get_generation_queue_stats(),
        "tasks": tasks
    }


@router.post("/generate-email")
def generate_email(body: GenerateEmailRequest):
    """Draft an application email for a job."""
    try:
        from src.generators.email import generate_application_email

        result = generate_application_email(
            company=body.company,
            position=body.position,
            description=body.description,
            job_url=body.job_url,
            explicit_email=body.email,
        )
        return result
    except Exception as e:
        logger.error(f"Error in /api/generate-email: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/answer-form-question")
def answer_form_question(body: AnswerFormQuestionRequest):
    """Answer an application form question using Gemini grounded in verified candidate profile."""
    question = (body.question or "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "Question cannot be empty."})

    try:
        from src.generators.form_copilot import generate_form_answer

        result = generate_form_answer(
            question=question,
            company=body.company,
            position=body.position,
            description=body.description,
            language=body.language,
        )
        if not result.get("success"):
            return JSONResponse(status_code=500, content={"error": result.get("error", "Failed to generate answer")})
        return result
    except Exception as e:
        logger.error(f"Error in /api/answer-form-question: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/generate-application")
def generate_application(body: GenerateApplicationRequest):
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

    try:
        from src.generators.application import _slugify

        today = datetime.now().strftime("%Y-%m-%d")
        comp_slug = _slugify(company, max_len=30)
        pos_slug = _slugify(position, max_len=35)
        base_name = f"{comp_slug}_{pos_slug}"
        if len(base_name) > 65:
            base_name = base_name[:65].rstrip('-')
        task_key = base_name

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
            register_application_in_crm(company, position, job_url, cv_rel, cover_rel, notes)
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
        )

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
        return JSONResponse(status_code=500, content={"error": str(e)})
