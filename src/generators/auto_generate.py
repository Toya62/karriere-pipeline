"""
src/generators/auto_generate.py

Automated ATS Application Generation Pipeline for high-scoring approved jobs (85%+).
Executes after scraping and AI evaluations complete, compiles tailored CVs + Cover Letters,
registers them in the CRM, synchronizes git, and sends a Telegram completion notification.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from src.core.logger import get_logger
from src.core.utils import GERMAN_TZ
from src.db.database import get_db_connection, is_postgres
from src.generators.application import generate_application
from src.dashboard.applications import register_application_in_crm
from src.dashboard.git_ops import git_sync_async
from src.core.notifier import send_telegram_alert

logger = get_logger(__name__)


def auto_generate_approved_applications(
    min_score: int = 85,
    max_age_days: int = 1,
    limit: int = 25,
    notify_telegram: bool = True,
    db_path: str = "data/karriere.db",
) -> Dict[str, Any]:
    """Finds all ungenerated approved jobs (score >= min_score) within the time window,

    generates tailored ATS CVs + Cover Letters via Gemini/Tectonic, registers them in CRM,
    and dispatches a Telegram notification.
    """
    logger.info(f"Starting auto-generation pipeline: min_score={min_score}, max_age_days={max_age_days}, limit={limit}")

    cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Query ungenerated approved jobs, filtering out duplicates
    query = """
    SELECT j.id, j.company, j.title, j.url, j.location, j.description, e.score, e.status, e.archetype
    FROM jobs j
    JOIN evaluations e ON e.job_id = j.id
    LEFT JOIN applications a ON a.job_id = j.id
    WHERE e.status LIKE 'APPROVED%' 
      AND e.score >= ?
      AND e.status != 'USER_DISMISSED'
      AND (a.id IS NULL OR a.cv_pdf_path IS NULL OR a.cv_pdf_path = '')
      AND (j.scraped_at IS NOT NULL AND j.scraped_at >= ?)
      AND NOT EXISTS (
          SELECT 1 FROM applications a2
          JOIN jobs j2 ON a2.job_id = j2.id
          WHERE a2.cv_pdf_path IS NOT NULL AND a2.cv_pdf_path != ''
            AND (
                LOWER(j.url) = LOWER(j2.url)
                OR (
                    LOWER(SUBSTR(j.title, 1, 20)) = LOWER(SUBSTR(j2.title, 1, 20))
                    AND (
                        LOWER(j.company) LIKE '%' || LOWER(SUBSTR(j2.company, 1, 5)) || '%'
                        OR LOWER(j2.company) LIKE '%' || LOWER(SUBSTR(j.company, 1, 5)) || '%'
                    )
                )
            )
      )
    ORDER BY e.score DESC, j.id DESC
    """

    cursor.execute(query, (min_score, cutoff))
    rows = cursor.fetchall()
    conn.close()

    total_candidates = len(rows)
    logger.info(f"Found {total_candidates} ungenerated approved jobs (>= {min_score}%) in current window (cutoff={cutoff}).")

    if total_candidates == 0:
        return {
            "total_candidates": 0,
            "generated_count": 0,
            "remaining_count": 0,
            "failed_count": 0,
            "generated_jobs": [],
        }

    to_process = rows[:limit]
    generated_jobs: List[Dict[str, Any]] = []
    failed_count = 0

    print(f"\n{'='*60}")
    print(f"  ⚡ Auto-Generating {len(to_process)} Application Packages (Score >= {min_score}%)")
    print(f"{'='*60}\n")

    for idx, row in enumerate(to_process, 1):
        job_id = row[0]
        company = str(row[1] or "").strip()
        title = str(row[2] or "").strip()
        url = str(row[3] or "").strip()
        location = str(row[4] or "").strip()
        description = str(row[5] or "").strip()
        score = row[6]

        print(f"[{idx}/{len(to_process)}] Generating tailored CV & Cover Letter for: {title} @ {company} ({score}%)...")

        try:
            res = generate_application(
                company=company,
                position=title,
                description=description,
                job_url=url,
                location=location,
                language=None,
                compile_pdf=True,
                clean_tex=True,
            )

            if res.get("success"):
                cv_p = res.get("cv_path", "")
                cov_p = res.get("cover_path", "")
                ats_keywords = res.get("ats_keywords", []) or []
                notes = f"ATS-tailored via Auto-Pipeline ({score}%)."
                if ats_keywords:
                    notes += " Keywords: " + ", ".join(ats_keywords[:6])
                if res.get("meta_path"):
                    notes += f" Meta: {res['meta_path']}"

                register_application_in_crm(
                    company=company,
                    position=title,
                    job_url=url,
                    cv_path=cv_p,
                    cover_path=cov_p,
                    notes=notes,
                )

                generated_jobs.append({
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "score": score,
                    "cv_path": cv_p,
                    "cover_path": cov_p,
                })
                print(f"  ✓ Successfully compiled: {cv_p}")
            else:
                failed_count += 1
                logger.error(f"  ✗ Failed generation for {title} @ {company}: {res.get('error')}")

        except Exception as gen_err:
            failed_count += 1
            logger.error(f"  ✗ Exception generating {title} @ {company}: {gen_err}")

    # Re-calculate remaining count
    remaining_count = max(0, total_candidates - len(generated_jobs))

    # Trigger git push for newly created PDFs
    if generated_jobs:
        git_sync_async(f"feat: auto-generated {len(generated_jobs)} ATS-tailored applications [85%+]")

    # Dispatch Telegram notification
    if notify_telegram and (generated_jobs or remaining_count > 0):
        try:
            gen_count = len(generated_jobs)
            lines = [
                "🎯 *Auto-Generation Pipeline Complete*",
                "",
                f"✅ *Generated Packages:* {gen_count} (CV + Anschreiben)",
                f"⏳ *Remaining in Queue (85%+):* {remaining_count}",
            ]
            if failed_count > 0:
                lines.append(f"⚠️ *Failed:* {failed_count}")

            if generated_jobs:
                lines.append("\n*Generated Applications:*")
                for j in generated_jobs[:10]:
                    safe_title = str(j.get("title", "")).replace("*", "").replace("_", " ").replace("`", "")
                    safe_company = str(j.get("company", "")).replace("*", "").replace("_", " ").replace("`", "")
                    lines.append(f"• *{safe_title}* @ {safe_company} ({j['score']}%)")
                if len(generated_jobs) > 10:
                    lines.append(f"• ... and {len(generated_jobs) - 10} more")

            msg = "\n".join(lines)
            send_telegram_alert(msg)
            logger.info("Sent auto-generation summary to Telegram.")
        except Exception as tel_err:
            logger.warning(f"Failed to send Telegram auto-generation notification: {tel_err}")

    return {
        "total_candidates": total_candidates,
        "generated_count": len(generated_jobs),
        "remaining_count": remaining_count,
        "failed_count": failed_count,
        "generated_jobs": generated_jobs,
    }
