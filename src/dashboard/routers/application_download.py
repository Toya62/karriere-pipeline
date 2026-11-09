"""Router for downloading application documents (single PDF and ZIP bundles)."""

import io
import os
import re
import zipfile
import urllib.parse
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from src.dashboard.routers.auth import get_current_user
from src.dashboard.git_ops import git_root
from src.db.database import get_db_connection

router = APIRouter(prefix="/api/applications", tags=["application-download"])


def _clean_filename(s: str) -> str:
    """Sanitize string for clean, cross-platform filenames."""
    s = re.sub(r'[\\/*?:"<>|]', "", str(s or ""))
    s = re.sub(r"\s+", "_", s.strip())
    return s[:60] or "Application"


def _resolve_existing_file(path_str: str | None) -> str | None:
    """Resolve file path against disk, root_dir, or applications/ folder."""
    if not path_str:
        return None
    p = str(path_str).strip()
    if p.startswith("/"):
        # Check absolute path first
        if os.path.exists(p) and os.path.isfile(p):
            return p
        p = p.lstrip("/")

    root = git_root()
    candidates = [
        os.path.join(root, p),
        os.path.join(root, "applications", p),
        os.path.abspath(p),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isfile(c):
            return c
    return None


@router.get("/{application_id}/download")
def download_application(
    application_id: int,
    type: str = Query("zip", pattern="^(zip|cv|cover)$"),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Download single PDF (CV or cover) or full ZIP package for an application."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required.")

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.id, a.user_id, a.cv_pdf_path, a.cover_pdf_path, j.company, j.title
            FROM applications a
            LEFT JOIN jobs j ON a.job_id = j.id
            WHERE a.id = ?
            """,
            (application_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Application #{application_id} not found.")

        app_user_id = row[1]
        if not is_admin and app_user_id and app_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied to this application.")

        cv_raw_path = row[2]
        cl_raw_path = row[3]
        company = row[4] or "Company"
        position = row[5] or "Position"

        cv_resolved = _resolve_existing_file(cv_raw_path)
        cl_resolved = _resolve_existing_file(cl_raw_path)

        comp_clean = _clean_filename(company)
        pos_clean = _clean_filename(position)

        if type == "cv":
            if not cv_resolved:
                raise HTTPException(status_code=404, detail="CV PDF not generated or missing on disk.")
            dl_name = f"{comp_clean}_{pos_clean}_CV.pdf"
            encoded_dl_name = urllib.parse.quote(dl_name)
            return FileResponse(
                cv_resolved,
                media_type="application/pdf",
                filename=dl_name,
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_dl_name}"},
            )

        if type == "cover":
            if not cl_resolved:
                raise HTTPException(status_code=404, detail="Cover Letter PDF not generated or missing on disk.")
            dl_name = f"{comp_clean}_{pos_clean}_Cover_Letter.pdf"
            encoded_dl_name = urllib.parse.quote(dl_name)
            return FileResponse(
                cl_resolved,
                media_type="application/pdf",
                filename=dl_name,
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_dl_name}"},
            )

        # type == "zip"
        if not cv_resolved and not cl_resolved:
            raise HTTPException(status_code=404, detail="No generated PDF files found for this application.")

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if cv_resolved:
                zf.write(cv_resolved, arcname=f"{comp_clean}_{pos_clean}_CV.pdf")
            if cl_resolved:
                zf.write(cl_resolved, arcname=f"{comp_clean}_{pos_clean}_Cover_Letter.pdf")

            # Check for adjacent .meta.json file
            target_meta = None
            if cv_resolved and cv_resolved.endswith("_cv.pdf"):
                meta_candidate = cv_resolved[:-7] + ".meta.json"
                if os.path.exists(meta_candidate):
                    target_meta = meta_candidate
            elif cl_resolved and cl_resolved.endswith("_cover.pdf"):
                meta_candidate = cl_resolved[:-10] + ".meta.json"
                if os.path.exists(meta_candidate):
                    target_meta = meta_candidate

            if target_meta:
                zf.write(target_meta, arcname=f"{comp_clean}_{pos_clean}_meta.json")

        zip_val = zip_buf.getvalue()
        zip_name = f"{comp_clean}_{pos_clean}_Application.zip"
        encoded_zip_name = urllib.parse.quote(zip_name)
        return Response(
            content=zip_val,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_zip_name}",
                "Content-Length": str(len(zip_val)),
            },
        )
    finally:
        conn.close()


@router.get("/export-batch")
def export_batch(
    status: str = Query("prepared"),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Export a ZIP bundle containing all applications matching status for current user."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required.")

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT a.id, a.cv_pdf_path, a.cover_pdf_path, j.company, j.title, a.status
            FROM applications a
            LEFT JOIN jobs j ON a.job_id = j.id
        """
        clauses = []
        params = []
        if not is_admin:
            clauses.append("(a.user_id = ? OR a.user_id IS NULL)")
            params.append(user_id)
        if status and status.lower() != "all":
            clauses.append("LOWER(a.status) = ?")
            params.append(status.lower())

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY a.id DESC LIMIT 100"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        zip_buf = io.BytesIO()
        bundled_count = 0
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in rows:
                cv_res = _resolve_existing_file(r[1])
                cl_res = _resolve_existing_file(r[2])
                if not cv_res and not cl_res:
                    continue

                company_clean = _clean_filename(r[3] or "Company")
                position_clean = _clean_filename(r[4] or "Position")
                folder = f"{company_clean}_{position_clean}"

                if cv_res:
                    zf.write(cv_res, arcname=f"{folder}/{company_clean}_CV.pdf")
                    bundled_count += 1
                if cl_res:
                    zf.write(cl_res, arcname=f"{folder}/{company_clean}_Cover_Letter.pdf")
                    bundled_count += 1

                # Check meta.json
                meta_candidate = None
                if cv_res and cv_res.endswith("_cv.pdf"):
                    cand = cv_res[:-7] + ".meta.json"
                    if os.path.exists(cand):
                        meta_candidate = cand
                if meta_candidate:
                    zf.write(meta_candidate, arcname=f"{folder}/meta.json")

        if bundled_count == 0:
            # Add an empty placeholder readme so zipfile is valid
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    "README.txt",
                    f"No compiled application files found for status '{status}'. Generate applications first from the CRM or Job Finder.",
                )

        zip_bytes = zip_buf.getvalue()
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        zip_filename = f"applications_{status}_{today_str}.zip"
        encoded_name = urllib.parse.quote(zip_filename)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
                "Content-Length": str(len(zip_bytes)),
            },
        )
    finally:
        conn.close()
