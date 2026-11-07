"""Router for managing candidate credential and supplementary documents (Master Urkunde, References, Transcripts)."""

import base64
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

DOCS_DIR = os.path.join("data", "documents")

DOCUMENT_TYPES = {
    "master_urkunde": {
        "title": "Master Urkunde / Degree Certificate",
        "filename": "master_urkunde.pdf",
        "description": "M.Sc. Computer & Systems Engineering certificate from TU Ilmenau.",
    },
    "job_references": {
        "title": "Job References / Arbeitszeugnisse",
        "filename": "job_references.pdf",
        "description": "Letters of recommendation & employer performance references.",
    },
    "transcripts": {
        "title": "Transcripts of Records",
        "filename": "transcripts.pdf",
        "description": "Complete university grade records and coursework breakdown.",
    },
    "other_certificates": {
        "title": "Other Certificates / Sonstige Zertifikate",
        "filename": "other_certificates.pdf",
        "description": "Professional certifications and extra credentials.",
    },
}


class DocumentUploadPayload(BaseModel):
    category: str
    filename: str = ""
    file_base64: str


def _get_doc_info(key: str) -> dict:
    meta = DOCUMENT_TYPES.get(key, {})
    filename = meta.get("filename", f"{key}.pdf")
    filepath = os.path.join(DOCS_DIR, filename)
    exists = os.path.isfile(filepath)
    size_bytes = os.path.getsize(filepath) if exists else 0

    size_human = "Not uploaded"
    if exists:
        if size_bytes >= 1024 * 1024:
            size_human = f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_human = f"{size_bytes / 1024:.0f} KB"

    return {
        "key": key,
        "title": meta.get("title", key),
        "filename": filename,
        "description": meta.get("description", ""),
        "exists": exists,
        "size_bytes": size_bytes,
        "size_human": size_human,
        "download_url": f"/api/documents/download/{filename}" if exists else None,
    }


@router.get("")
def list_documents():
    """List all credential documents with their availability and size."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    return {
        "documents": [_get_doc_info(k) for k in DOCUMENT_TYPES]
    }


@router.post("/upload")
async def upload_document(payload: DocumentUploadPayload):
    """Upload or replace a credential document via JSON Base64."""
    category = payload.category
    if category not in DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Must be one of: {list(DOCUMENT_TYPES.keys())}"
        )

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

    os.makedirs(DOCS_DIR, exist_ok=True)
    target_filename = DOCUMENT_TYPES[category]["filename"]
    target_path = os.path.join(DOCS_DIR, target_filename)

    with open(target_path, "wb") as f:
        f.write(content)

    logger.info(f"Uploaded {category} document to {target_path} ({len(content)} bytes)")
    return {
        "success": True,
        "category": category,
        "document": _get_doc_info(category),
    }


@router.get("/download/{filename}")
def download_document(filename: str):
    """Download a credential document."""
    clean_name = os.path.basename(filename)
    if clean_name != filename or not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = os.path.join(DOCS_DIR, clean_name)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Document not found")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=f"Toyanath_Pandey_{clean_name}",
        headers={"Cache-Control": "no-cache"},
    )

