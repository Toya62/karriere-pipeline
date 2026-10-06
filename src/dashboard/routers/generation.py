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
    GenerateApplicationRequest,
    GenerateEmailRequest,
)
from src.dashboard.state import APP_GEN_STATUS, set_gen_status

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["generation"])


@router.get("/generate-application/status")
def generation_status(task_key: str = Query("")):
    """Poll the status of a background application-generation task."""
    if not task_key:
        return JSONResponse(status_code=400, content={"error": "Missing task_key parameter"})
    return APP_GEN_STATUS.get(task_key, {"status": "not_found", "message": "No generation task found"})


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
        comp_slug = _slugify(company)
        pos_slug = _slugify(position)
        base_name = f"{comp_slug}_{pos_slug}"
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

        if task_key in APP_GEN_STATUS and APP_GEN_STATUS[task_key].get("status") == "running":
            return {
                "success": True,
                "status": "running",
                "task_key": task_key,
                "message": "Generation already in progress...",
            }

        set_gen_status(task_key, {
            "status": "running",
            "message": "Analyzing ATS keywords & generating tailored application...",
            "company": company,
            "position": position,
            "started_at": datetime.now().isoformat(),
        })

        launch_application_generation(
            company=company,
            position=position,
            description=description,
            job_url=job_url,
            location=location,
            language=language,
            task_key=task_key,
        )

        return JSONResponse(status_code=202, content={
            "success": True,
            "status": "generating",
            "task_key": task_key,
            "message": f"Generating ATS-tailored application for {company}...",
        })
    except Exception as e:
        logger.error(f"Error in /api/generate-application: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
