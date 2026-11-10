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
        if os.getenv("MULTI_USER_MODE", "").lower() != "true":
            user_id = 1
            is_admin = True
        else:
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


def _get_available_dates() -> list[str]:
    """Return all date folders under applications/ sorted descending."""
    root = git_root()
    app_root = os.path.join(root, "applications")
    if not os.path.exists(app_root):
        return []
    dates = []
    for entry in os.listdir(app_root):
        if re.match(r"^\d{4}-\d{2}-\d{2}$", entry):
            dir_path = os.path.join(app_root, entry)
            if os.path.isdir(dir_path):
                has_files = any(
                    f.endswith(".pdf") or f.endswith(".meta.json")
                    for f in os.listdir(dir_path)
                )
                if has_files:
                    dates.append(entry)
    dates.sort(reverse=True)
    return dates


def _bundle_date_folder(date_str: str, zip_buf: io.BytesIO, user_id: int = 1) -> tuple[int, str]:
    """Bundle all application documents in applications/{date_str} and auto-sync into DB."""
    import json
    root = git_root()
    app_root = os.path.join(root, "applications")
    available = _get_available_dates()

    target_date = date_str
    if target_date in ("today", "latest"):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if target_date == "today" and today in available:
            target_date = today
        elif available:
            target_date = available[0]  # Most recent non-empty date folder
        else:
            target_date = today

    date_dir = os.path.join(app_root, target_date)
    if not os.path.exists(date_dir) or not os.path.isdir(date_dir):
        return 0, target_date

    files = os.listdir(date_dir)
    meta_files = [f for f in files if f.endswith(".meta.json")]

    bundled = 0
    processed_stems = set()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for mf in sorted(meta_files):
            stem = mf[:-10]
            processed_stems.add(stem)
            meta_path = os.path.join(date_dir, mf)
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}

            company = meta.get("company") or stem.split("_")[0]
            position = meta.get("position") or meta.get("title") or "Application"
            comp_clean = _clean_filename(company)
            pos_clean = _clean_filename(position)
            folder = f"{comp_clean}_{pos_clean}"

            cv_name = f"{stem}_cv.pdf"
            cl_name = f"{stem}_cover.pdf"
            cv_path = os.path.join(date_dir, cv_name)
            cl_path = os.path.join(date_dir, cl_name)

            has_doc = False
            if os.path.exists(cv_path):
                zf.write(cv_path, arcname=f"{folder}/{comp_clean}_CV.pdf")
                bundled += 1
                has_doc = True
            if os.path.exists(cl_path):
                zf.write(cl_path, arcname=f"{folder}/{comp_clean}_Cover_Letter.pdf")
                bundled += 1
                has_doc = True
            if has_doc or os.path.exists(meta_path):
                zf.write(meta_path, arcname=f"{folder}/{comp_clean}_meta.json")

            # Queue auto-sync to CRM DB in background so ZIP generation stays fast
            try:
                rel_cv = os.path.relpath(cv_path, root) if os.path.exists(cv_path) else ""
                rel_cl = os.path.relpath(cl_path, root) if os.path.exists(cl_path) else ""
                job_u = meta.get("job_url", "") or meta.get("apply_url", "")
                import threading
                def _bg_sync(c=company, p=position, u=job_u, cv=rel_cv, cl=rel_cl, d=target_date, uid=user_id):
                    try:
                        from src.dashboard.crm import upsert_tracker_row
                        upsert_tracker_row(
                            company=c,
                            position=p,
                            job_url=u,
                            cv_path=cv,
                            cover_path=cl,
                            status="Prepared",
                            date_applied=d,
                            create=True,
                            user_id=uid,
                        )
                    except Exception:
                        pass
                threading.Thread(target=_bg_sync, daemon=True).start()
            except Exception:
                pass

        # Handle any stray PDFs without meta files
        for f in sorted(files):
            if f.endswith(".pdf") and not any(f.startswith(s) for s in processed_stems):
                pdf_path = os.path.join(date_dir, f)
                zf.write(pdf_path, arcname=f"other/{f}")
                bundled += 1

    return bundled, target_date


@router.get("/export-dates")
def get_export_dates(current_user: dict[str, Any] = Depends(get_current_user)):
    """List all available application date folders available for ZIP download."""
    dates = _get_available_dates()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    latest_date = dates[0] if dates else today_str
    return {
        "dates": dates,
        "latest": latest_date,
        "today": today_str,
        "has_applications": len(dates) > 0,
    }


@router.get("/export-batch")
def export_batch(
    status: str | None = Query(None),
    date: str | None = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Export a ZIP bundle containing applications by date folder or status."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"
    if user_id <= 0:
        if os.getenv("MULTI_USER_MODE", "").lower() != "true":
            user_id = 1
            is_admin = True
        else:
            raise HTTPException(status_code=401, detail="Authentication required.")

    zip_buf = io.BytesIO()

    # Normalize query inputs against FastAPI Query objects or empty strings
    date_str = str(date).strip() if (isinstance(date, str) and str(date).strip()) else None
    status_str = str(status).strip() if (isinstance(status, str) and str(status).strip()) else None

    # Priority 1: Date-based export (today, latest, or exact YYYY-MM-DD)
    if date_str and date_str.lower() not in ("all", "any", ""):
        bundled_count, resolved_date = _bundle_date_folder(date_str, zip_buf, user_id=user_id)
        if bundled_count > 0:
            zip_bytes = zip_buf.getvalue()
            zip_filename = f"applications_{resolved_date}.zip"
            encoded_name = urllib.parse.quote(zip_filename)
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
                    "Content-Length": str(len(zip_bytes)),
                },
            )

    # Priority 2: Database status export (or fallback to latest date on disk if DB empty)
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
        if status_str and status_str.lower() not in ("all", "any"):
            if status_str.lower() == "prepared":
                clauses.append("(LOWER(COALESCE(a.status, '')) IN ('prepared', 'draft', 'not applied', ''))")
            else:
                clauses.append("LOWER(a.status) = ?")
                params.append(status_str.lower())

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY a.id DESC LIMIT 100"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        bundled_count = 0
        seen_arcnames = set()
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
                    cv_arc = f"{folder}/{company_clean}_CV.pdf"
                    if cv_arc not in seen_arcnames:
                        zf.write(cv_res, arcname=cv_arc)
                        seen_arcnames.add(cv_arc)
                        bundled_count += 1
                if cl_res:
                    cl_arc = f"{folder}/{company_clean}_Cover_Letter.pdf"
                    if cl_arc not in seen_arcnames:
                        zf.write(cl_res, arcname=cl_arc)
                        seen_arcnames.add(cl_arc)
                        bundled_count += 1

                meta_candidate = None
                if cv_res and cv_res.endswith("_cv.pdf"):
                    cand = cv_res[:-7] + ".meta.json"
                    if os.path.exists(cand):
                        meta_candidate = cand
                if meta_candidate:
                    meta_arc = f"{folder}/meta.json"
                    if meta_arc not in seen_arcnames:
                        zf.write(meta_candidate, arcname=meta_arc)
                        seen_arcnames.add(meta_arc)

        # If DB had 0 matching files, fall back to the latest on-disk date folder!
        if bundled_count == 0:
            zip_buf = io.BytesIO()
            bundled_count, resolved_date = _bundle_date_folder("latest", zip_buf, user_id=user_id)
            if bundled_count > 0:
                zip_bytes = zip_buf.getvalue()
                zip_filename = f"applications_latest_{resolved_date}.zip"
                encoded_name = urllib.parse.quote(zip_filename)
                return Response(
                    content=zip_bytes,
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
                        "Content-Length": str(len(zip_bytes)),
                    },
                )

        if bundled_count == 0:
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    "README.txt",
                    f"No application files found on disk or database. Generate applications first from the CRM or Job Finder.",
                )

        zip_bytes = zip_buf.getvalue()
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        zip_filename = f"applications_{status or 'all'}_{today_str}.zip"
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
