"""Router for managing candidate credential and supplementary documents (Master Urkunde, References, Transcripts).

Supports multi-tenant isolation and Cloudflare R2 cloud object storage with local disk fallback.
"""

import base64
import os
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.core.logger import get_logger
from src.core.r2_storage import (
    delete_user_document_from_r2,
    generate_presigned_download_url,
    get_user_document_from_r2,
    is_r2_configured,
    upload_user_document_to_r2,
)
from src.dashboard.routers.auth import get_current_user
from src.db.database import (
    delete_user_document,
    get_user_documents,
    save_user_document,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

DOCS_DIR = os.path.join("data", "documents")

DOCUMENT_TYPES = {
    "master_cv": {
        "title": "Master Curriculum Vitae",
        "filename": "master_cv.pdf",
        "description": "General master resume / CV for direct ATS submission fallback.",
        "fallback_filenames": ["master_cv.pdf", "cv.pdf", "lebenslauf.pdf"],
    },
    "degree_certificate": {
        "title": "Degree Certificate",
        "filename": "degree_certificate.pdf",
        "description": "Official Bachelor's or Master's degree diploma and graduation certificate.",
        "fallback_filenames": ["degree_certificate.pdf", "master_urkunde.pdf"],
    },
    "transcripts": {
        "title": "Transcript of Records",
        "filename": "transcripts.pdf",
        "description": "Official academic grade transcript and completed coursework records.",
        "fallback_filenames": ["transcripts.pdf"],
    },
    "job_references": {
        "title": "Job References",
        "filename": "job_references.pdf",
        "description": "Letters of recommendation and employer performance references.",
        "fallback_filenames": ["job_references.pdf", "arbeitszeugnisse.pdf"],
    },
    "certifications": {
        "title": "Certifications & Credentials",
        "filename": "certifications.pdf",
        "description": "Professional certifications, licenses, and training credentials.",
        "fallback_filenames": ["certifications.pdf", "other_certificates.pdf"],
    },
}

CATEGORY_ALIASES = {
    "master_urkunde": "degree_certificate",
    "other_certificates": "certifications",
    "arbeitszeugnisse": "job_references",
}


class DocumentUploadPayload(BaseModel):
    category: str
    filename: str = ""
    file_base64: str


def _user_doc_path(user_id: int, filename: str) -> str:
    """Return local filesystem path for user's document."""
    if user_id == 1:
        return os.path.join(DOCS_DIR, filename)
    return os.path.join(DOCS_DIR, str(user_id), filename)


def _get_doc_info(key: str, user_id: int = 0, is_admin: bool = False, db_docs_by_cat: dict[str, dict] | None = None) -> dict[str, Any]:
    meta = DOCUMENT_TYPES.get(key, {})
    default_filename = meta.get("filename", f"{key}.pdf")

    db_doc = (db_docs_by_cat or {}).get(key)
    if not db_doc and db_docs_by_cat:
        for alias, target in CATEGORY_ALIASES.items():
            if target == key and alias in db_docs_by_cat:
                db_doc = db_docs_by_cat[alias]
                break

    filename = db_doc.get("filename") if db_doc else default_filename
    r2_key = db_doc.get("r2_key") if db_doc else ""

    local_path = ""
    candidate_filenames = meta.get("fallback_filenames", [default_filename])
    for fname in candidate_filenames:
        c_path = _user_doc_path(user_id, fname)
        if not os.path.isfile(c_path) and is_admin and os.path.isfile(os.path.join(DOCS_DIR, fname)):
            c_path = os.path.join(DOCS_DIR, fname)
        if os.path.isfile(c_path):
            local_path = c_path
            default_filename = fname
            break

    if not local_path:
        local_path = _user_doc_path(user_id, default_filename)

    exists_local = bool(local_path and os.path.isfile(local_path))
    exists = bool(db_doc or exists_local)
    size_bytes = 0

    if exists_local:
        size_bytes = os.path.getsize(local_path)
    elif db_doc and db_doc.get("file_size"):
        size_bytes = int(db_doc["file_size"])

    size_human = "Not uploaded"
    if exists:
        if size_bytes >= 1024 * 1024:
            size_human = f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_human = f"{size_bytes / 1024:.0f} KB"

    download_url = f"/api/documents/download/{default_filename}" if exists else None
    presigned_url = None
    if r2_key and is_r2_configured():
        presigned_url = generate_presigned_download_url(r2_key)

    return {
        "key": key,
        "title": meta.get("title", key),
        "filename": default_filename,
        "description": meta.get("description", ""),
        "exists": exists,
        "size_bytes": size_bytes,
        "size_human": size_human,
        "download_url": download_url,
        "presigned_url": presigned_url,
        "storage": "r2" if r2_key else "local",
    }


@router.get("")
def list_documents(current_user: dict[str, Any] = Depends(get_current_user)):
    """List all credential documents with their availability and size for current user."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    user_id = current_user.get("id", 0)
    if not user_id or user_id <= 0:
        return {
            "user_id": 0,
            "documents": [
                {
                    "key": k,
                    "title": DOCUMENT_TYPES[k]["title"],
                    "filename": DOCUMENT_TYPES[k]["filename"],
                    "description": DOCUMENT_TYPES[k]["description"],
                    "exists": False,
                    "size_bytes": 0,
                    "size_human": "Not uploaded",
                    "download_url": None,
                    "presigned_url": None,
                    "storage": "none",
                }
                for k in DOCUMENT_TYPES
            ],
        }

    is_admin = current_user.get("role") == "admin"
    db_docs = get_user_documents(user_id)
    db_by_cat = {d["category"]: d for d in db_docs}

    return {
        "user_id": user_id,
        "documents": [_get_doc_info(k, user_id=user_id, is_admin=is_admin, db_docs_by_cat=db_by_cat) for k in DOCUMENT_TYPES],
    }


@router.post("/upload")
async def upload_document(
    payload: DocumentUploadPayload,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Upload or replace a credential document via JSON Base64."""
    user_id = current_user.get("id", 0)
    if not user_id or user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required to upload documents")

    raw_cat = payload.category.lower().strip()
    category = CATEGORY_ALIASES.get(raw_cat, raw_cat)
    if category not in DOCUMENT_TYPES:
        valid_cats = list(DOCUMENT_TYPES.keys()) + list(CATEGORY_ALIASES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{raw_cat}'. Must be one of: {valid_cats}",
        )

    user_id = current_user.get("id", 1)

    # Clean base64 header if present (e.g. data:application/pdf;base64,...)
    raw_b64 = payload.file_base64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        content = base64.b64decode(raw_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 encoding: {e}")

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Only valid PDF documents are accepted.")

    target_filename = DOCUMENT_TYPES[category]["filename"]

    # 1. Save local copy
    local_path = _user_doc_path(user_id, target_filename)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(content)

    # 2. Upload to Cloudflare R2 if configured and user has PRO entitlement
    from src.core.entitlements import get_user_tier
    is_pro = get_user_tier(current_user) == "pro"
    r2_key = ""
    if is_r2_configured() and is_pro:
        r2_key = upload_user_document_to_r2(
            user_id=user_id,
            category=category,
            filename=target_filename,
            content=content,
            content_type="application/pdf",
        ) or ""

    # 3. Save entry in database
    saved_doc = save_user_document(
        user_id=user_id,
        category=category,
        filename=target_filename,
        r2_key=r2_key,
        file_size=len(content),
        content_type="application/pdf",
    )

    logger.info(f"User {user_id} uploaded {category} document ({len(content)} bytes, R2: {bool(r2_key)})")
    return {
        "success": True,
        "category": category,
        "document": _get_doc_info(category, user_id=user_id, db_docs_by_cat={category: saved_doc}),
    }


@router.get("/download/{filename}")
def download_document(
    filename: str,
    inline: bool = True,
    download: bool = False,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Download or view a credential document for the current user."""
    clean_name = os.path.basename(filename)
    if clean_name != filename or not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"
    if not user_id or user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required to download documents")

    disposition = "attachment" if (download or not inline) else "inline"

    # 1. Try local filesystem (check requested filename and fallbacks)
    candidate_names = [clean_name]
    for meta in DOCUMENT_TYPES.values():
        fallbacks = meta.get("fallback_filenames", [])
        if clean_name in fallbacks:
            candidate_names.extend(fallbacks)
    candidate_names = list(dict.fromkeys(candidate_names))

    for c_name in candidate_names:
        local_path = _user_doc_path(user_id, c_name)
        if not os.path.isfile(local_path) and is_admin and os.path.isfile(os.path.join(DOCS_DIR, c_name)):
            local_path = os.path.join(DOCS_DIR, c_name)
        if os.path.isfile(local_path):
            headers = {
                "Cache-Control": "no-cache",
                "Content-Disposition": f'{disposition}; filename="Candidate_{clean_name}"',
            }
            return FileResponse(
                local_path,
                media_type="application/pdf",
                headers=headers,
            )

    # 2. Try fetching from Cloudflare R2 via user_documents
    db_docs = get_user_documents(user_id)
    matching = [d for d in db_docs if d.get("filename") == clean_name or f"{d.get('category')}.pdf" == clean_name]
    if matching and matching[0].get("r2_key"):
        content = get_user_document_from_r2(matching[0]["r2_key"])
        if content:
            return Response(
                content=content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'{disposition}; filename="Candidate_{clean_name}"',
                    "Cache-Control": "no-cache",
                },
            )

    raise HTTPException(status_code=404, detail="Document not found")


@router.delete("/{category}")
def delete_document(
    category: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Delete a credential document for the current user."""
    user_id = current_user.get("id", 0)
    if not user_id or user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required to delete documents")

    raw_cat = category.lower().strip()
    canon_cat = CATEGORY_ALIASES.get(raw_cat, raw_cat)
    if canon_cat not in DOCUMENT_TYPES:
        valid_cats = list(DOCUMENT_TYPES.keys()) + list(CATEGORY_ALIASES.keys())
        raise HTTPException(status_code=400, detail=f"Invalid category '{category}'. Valid: {valid_cats}")

    meta = DOCUMENT_TYPES[canon_cat]

    # 1. Delete from Cloudflare R2 if present
    db_docs = get_user_documents(user_id)
    target_docs = [d for d in db_docs if d.get("category") in (canon_cat, raw_cat)]
    for d in target_docs:
        r2_key = d.get("r2_key")
        if r2_key and is_r2_configured():
            try:
                delete_user_document_from_r2(r2_key)
            except Exception as e:
                logger.warning(f"Failed deleting R2 object {r2_key}: {e}")

    # 2. Delete local files
    candidate_filenames = meta.get("fallback_filenames", [meta.get("filename", f"{canon_cat}.pdf")])
    for fname in candidate_filenames:
        local_path = _user_doc_path(user_id, fname)
        if os.path.isfile(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                logger.warning(f"Failed deleting local document {local_path}: {e}")

    # 3. Delete from database
    delete_user_document(user_id, canon_cat)
    if raw_cat != canon_cat:
        delete_user_document(user_id, raw_cat)

    logger.info(f"User {user_id} deleted document '{canon_cat}'")
    return {
        "success": True,
        "category": canon_cat,
        "message": f"Document {meta.get('title', canon_cat)} deleted successfully.",
    }

