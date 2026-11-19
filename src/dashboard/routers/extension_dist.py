"""Extension distribution router for direct in-app download and installation info."""

import io
import json
import os
import zipfile
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from src.dashboard.git_ops import git_root

router = APIRouter(prefix="/api/extension", tags=["extension-distribution"])


def _get_extension_dir() -> Path:
    root = Path(git_root())
    ext_dir = root / "extension"
    if not ext_dir.is_dir():
        ext_dir = Path.cwd() / "extension"
    if not ext_dir.is_dir():
        raise HTTPException(status_code=404, detail="Extension directory not found")
    return ext_dir


@router.get("/info")
def get_extension_info():
    """Return extension metadata, version, and download endpoint."""
    ext_dir = _get_extension_dir()
    manifest_path = ext_dir / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass
    return {
        "version": manifest.get("version", "1.4.1"),
        "manifest_name": manifest.get("name", "Sarathi — AI Career & ATS Auto-Fill"),
        "download_url": "/api/extension/download",
    }


@router.get("/download")
def download_extension_zip():
    """Stream clean in-memory zip archive containing extension/ files for Load Unpacked installation."""
    ext_dir = _get_extension_dir()
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ext_dir):
            # Exclude unwanted directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files):
                # Exclude macOS and editor artifacts
                if f.startswith(".") or f.endswith("~") or f.endswith(".pyc"):
                    continue
                file_path = Path(root) / f
                arcname = file_path.relative_to(ext_dir).as_posix()
                zf.write(file_path, arcname)

    zip_content = buf.getvalue()
    return Response(
        content=zip_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="sarathi-extension.zip"',
            "Content-Length": str(len(zip_content)),
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
