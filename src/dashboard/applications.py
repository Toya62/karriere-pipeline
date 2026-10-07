"""Application-side effects for the dashboard API.

Thin service layer around the CRM persistence helpers: it registers generated
applications, resolves an existing CV PDF on disk, and runs the background
generation worker. Keeping it out of the routers avoids circular imports and
lets the CLI/compiler paths reuse the same registration semantics.
"""

import os
import re
import threading
from datetime import datetime

from src.core.logger import get_logger
from src.dashboard.crm import UNSET, upsert_tracker_row
from src.dashboard.state import clear_data_caches, set_gen_status

logger = get_logger(__name__)


def register_application_in_crm(company: str, position: str, job_url: str,
                                cv_path: str, cover_path: str, notes: str = "") -> None:
    """Insert or update a generated application in the CRM SQLite tracker.

    Writes only the affected row (see ``upsert_tracker_row``); existing
    company/title keys and every other application are left untouched.
    """
    try:
        ok = upsert_tracker_row(
            company=company,
            position=position,
            job_url=job_url,
            cv_path=cv_path or UNSET,
            cover_path=cover_path or UNSET,
            notes=notes or UNSET,
        )
        if ok:
            clear_data_caches()
            logger.info(f"  ✓ Registered {company} — {position} in CRM tracker")
        else:
            logger.warning(f"  CRM registration skipped (unresolved): {company} — {position}")
    except Exception as crm_err:
        logger.warning(f"  CRM registration failed: {crm_err}")


_COMPANY_EXPANSIONS = {
    "ukhd": "universitatsklinikum-heidelberg",
    "ldbv": "landesamt-fur-digitalisierung-breitband-und-vermessung",
    "kkh": "kaufmannische-krankenkasse",
}


def _norm_txt(t) -> str:
    if not t:
        return ""
    return re.sub(r'[^a-z0-9]+', '-', str(t).lower()).strip('-')


def autoresolve_cv_pdf(company: str, position: str) -> str:
    """Find the newest matching ``*_cv.pdf`` under ``applications/`` if any.

    Mirrors the original dashboard heuristic: normalise company/title, apply a
    small expansion table for known abbreviations, then require an exact company
    match plus either an exact title match or a 50%+ word overlap.
    """
    apps_dir = 'applications'
    if not os.path.exists(apps_dir):
        return ""

    target_company = _norm_txt(company)
    target_position = _norm_txt(position)

    for folder in os.listdir(apps_dir):
        folder_path = os.path.join(apps_dir, folder)
        if not (os.path.isdir(folder_path) and re.match(r'\d{4}-\d{2}-\d{2}', folder)):
            continue
        for file in os.listdir(folder_path):
            if not file.endswith('_cv.pdf'):
                continue
            name_parts = file.replace('_cv.pdf', '').split('_')
            file_company = _norm_txt(name_parts[0]) if len(name_parts) > 0 else ""
            file_title = _norm_txt(name_parts[1]) if len(name_parts) > 1 else ""

            resolved_file_company = _COMPANY_EXPANSIONS.get(file_company, file_company)

            exact_company = bool(
                resolved_file_company
                and (resolved_file_company in target_company or target_company in resolved_file_company)
            )
            exact_title = bool(file_title and (file_title in target_position or target_position in file_title))

            word_match = False
            if exact_company and file_title and target_position:
                file_words = [w for w in file_title.split('-') if len(w) >= 3]
                job_words = target_position.split('-')
                if file_words:
                    match_count = sum(1 for w in file_words if w in job_words)
                    if match_count / len(file_words) >= 0.5:
                        word_match = True

            if exact_company and (exact_title or word_match):
                return f"applications/{folder}/{file}"
    return ""


def run_application_generation(company: str, position: str, description: str, job_url: str,
                               location: str, language, task_key: str) -> None:
    """Background worker that generates an application and records it in the CRM.

    Intended to run in a daemon thread launched by the generation router.
    """
    try:
        from src.dashboard.git_ops import git_sync_async
        from src.generators.application import generate_application

        result = generate_application(
            company=company,
            position=position,
            description=description,
            job_url=job_url,
            location=location,
            language=language,
            compile_pdf=True,
            clean_tex=True,
        )
        if result.get("success"):
            try:
                ats_keywords = result.get("ats_keywords", []) or []
                notes = "ATS-tailored via Dashboard."
                if ats_keywords:
                    notes += " Keywords: " + ", ".join(ats_keywords[:6])
                if result.get("meta_path"):
                    notes += f" Meta: {result['meta_path']}"
                register_application_in_crm(
                    company=company,
                    position=position,
                    job_url=job_url,
                    cv_path=result.get("cv_path", ""),
                    cover_path=result.get("cover_path", ""),
                    notes=notes,
                )
            except Exception as crm_err:
                logger.warning(f"  CRM auto-register failed: {crm_err}")

        # Publish completion only AFTER the CRM write so the dashboard's
        # post-complete refresh can never race it.
        set_gen_status(task_key, {
            "status": "complete" if result.get("success") else "error",
            "message": result.get("summary") or result.get("error", "Complete"),
            "result": result,
            "company": company,
            "position": position,
            "completed_at": datetime.now().isoformat(),
        })
        if result.get("success"):
            git_sync_async("feat: generated ATS-tailored application [auto]")
    except Exception as gen_err:
        logger.error(f"Application generation thread error: {gen_err}")
        set_gen_status(task_key, {
            "status": "error",
            "message": str(gen_err),
            "company": company,
            "position": position,
            "completed_at": datetime.now().isoformat(),
        })


def launch_application_generation(company: str, position: str, description: str, job_url: str,
                                  location: str, language, task_key: str) -> None:
    """Start :func:`run_application_generation` on a daemon background thread."""
    threading.Thread(
        target=run_application_generation,
        args=(company, position, description, job_url, location, language, task_key),
        daemon=True,
    ).start()
