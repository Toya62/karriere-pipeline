"""FastAPI application for the Karriere Pipeline dashboard.

Mounts the JSON API routers, serves the static SPA assets and application PDFs,
and applies the loopback-only CORS policy. The public entrypoint lives in
:mod:`src.dashboard.server`.

Run standalone for development with::

    uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8000
"""

import os
import sys
import threading
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logger import get_logger
from src.dashboard import state
from src.dashboard.git_ops import (
    GIT_LOCK,
    git_current_branch,
    git_in_progress,
    git_root,
    safe_pull_rebase,
)
from src.dashboard.routers import ALL_ROUTERS

logger = get_logger(__name__)

MAX_BODY_BYTES = 10 * 1024 * 1024
CACHE_CONTROL = "no-cache, no-store, must-revalidate"

STATIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


# --------------------------------------------------------------------------- #
# Asset resolution
# --------------------------------------------------------------------------- #
def _dashboard_asset_path(asset: str) -> str:
    """Resolve dashboard assets from a checkout or an installed distribution."""
    checkout_path = os.path.join(os.getcwd(), "dashboard", asset)
    if os.path.isfile(checkout_path):
        return checkout_path
    return os.path.join(sys.prefix, "dashboard", asset)


def _application_pdf_path(request_path: str) -> str | None:
    """Resolve a safe, repo-local ``applications/**/*.pdf`` path (or ``None``).

    Rejects traversal, non-PDF suffixes, and symlinks escaping ``applications/``.
    """
    relative_path = urllib.parse.unquote(request_path).lstrip("/")
    if "\\" in relative_path or not relative_path.startswith("applications/"):
        return None
    requested_relative_path = relative_path[len("applications/"):]
    components = requested_relative_path.split("/")
    if not requested_relative_path or any(component in {"", ".", ".."} for component in components):
        return None
    if Path(requested_relative_path).suffix.lower() != ".pdf":
        return None

    applications_root = Path(os.getcwd(), "applications").resolve()
    for candidate in applications_root.rglob("*"):
        if candidate.is_symlink() or candidate.suffix.lower() != ".pdf" or not candidate.is_file():
            continue
        try:
            resolved_candidate = candidate.resolve(strict=True)
            resolved_candidate.relative_to(applications_root)
            candidate_relative_path = candidate.relative_to(applications_root).as_posix()
        except (OSError, ValueError):
            continue
        if candidate_relative_path == requested_relative_path:
            return str(resolved_candidate)
    return None


# --------------------------------------------------------------------------- #
# CORS policy (loopback-only)
# --------------------------------------------------------------------------- #
_ALLOWED_ORIGINS = {
    "http://localhost",
    "https://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
    "http://localhost:3000",
    "https://localhost:3000",
    "http://127.0.0.1:3000",
    "https://127.0.0.1:3000",
    "http://localhost:8000",
    "https://localhost:8000",
    "http://127.0.0.1:8000",
    "https://127.0.0.1:8000",
}


def _cors_origin_header(origin: str) -> str | None:
    """Return the echoed origin when it is an allowed loopback origin."""
    return origin if origin in _ALLOWED_ORIGINS else None


def _is_origin_allowed(origin: str) -> bool:
    if not origin:
        return True
    return _cors_origin_header(origin) is not None


class DashboardCORSMiddleware(BaseHTTPMiddleware):
    """Loopback CORS handling with an explicit 403 for disallowed preflights."""

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("Origin", "")
        cors_origin = _cors_origin_header(origin)

        if request.method == "OPTIONS":
            if origin and not _is_origin_allowed(origin):
                return Response(status_code=403)
            response = Response(status_code=204)
        else:
            response = await call_next(request)

        if cors_origin:
            response.headers["Access-Control-Allow-Origin"] = cors_origin
            response.headers["Vary"] = "Origin"
        elif not origin:
            response.headers["Access-Control-Allow-Origin"] = "http://localhost:8000"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies with a JSON 413 before routing."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("Content-Length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"error": "Invalid Content-Length header"})
            if length < 0 or length > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"error": f"Payload exceeds limit ({MAX_BODY_BYTES} bytes)"},
                )
        return await call_next(request)


# --------------------------------------------------------------------------- #
# Background workers
# --------------------------------------------------------------------------- #
def _prewarm_cache() -> None:
    """Verify SQLite database connectivity at server startup."""
    def _load():
        try:
            import sqlite3
            db_path = os.path.join('data', 'karriere.db')
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM jobs")
                cnt = cursor.fetchone()[0]
                conn.close()
                logger.info(f"Database prewarm check: {cnt} jobs in SQLite data/karriere.db")
        except Exception as e:
            logger.debug(f"Cache pre-warm check error: {e}")

    threading.Thread(target=_load, daemon=True).start()


def _auto_pull_worker() -> None:
    """Periodically pull fresh data from origin/main in the background."""
    root_dir = git_root()
    while True:
        try:
            time.sleep(60)
            with GIT_LOCK:
                # Never touch a repo that is mid-operation or on a feature branch.
                branch = git_current_branch(root_dir)
                if branch not in ("main", "master") or git_in_progress(root_dir):
                    continue
                import subprocess
                subprocess.run(["git", "fetch", "origin", "main"], cwd=root_dir, capture_output=True)
                res = subprocess.run(["git", "log", "HEAD..origin/main", "--oneline"],
                                     cwd=root_dir, capture_output=True, text=True)
                new_commits = res.stdout.strip()
                if new_commits:
                    logger.info(f"[Auto-Pull] Detected new commits on origin/main:\n{new_commits}")
                    ok, detail = safe_pull_rebase(root_dir)
                    if ok:
                        logger.info("✓ [Auto-Pull] Successfully synchronized local repository with latest GitHub commits!")
                        try:
                            from src.db import sync_remote_git_db
                            sync_remote_git_db()
                        except Exception as sync_err:
                            logger.warning(f"[Auto-Pull] DB sync error: {sync_err}")
                        state.CACHE["jobs"].clear()
                    else:
                        logger.warning(f"[Auto-Pull] {detail}")
        except Exception as e:
            logger.debug(f"Auto-pull background check error: {e}")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _prewarm_cache()
    if os.environ.get("KARRIERE_GIT_SYNC", "true").lower() not in {"0", "false", "no"}:
        threading.Thread(target=_auto_pull_worker, daemon=True).start()
    yield


# --------------------------------------------------------------------------- #
# Application factory
# --------------------------------------------------------------------------- #
def create_app() -> FastAPI:
    """Build the dashboard FastAPI application."""
    app = FastAPI(title="Karriere Pipeline Dashboard", version="2.0.0", lifespan=_lifespan)

    # Innermost first: CORS wraps the size guard so preflights and 413s still
    # carry the loopback CORS headers.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(DashboardCORSMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON payload: {exc.errors()}"})

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error on {request.url.path}: {exc}")
        return JSONResponse(status_code=500, content={"error": str(exc)})

    def _serve_static(asset: str, content_type: str):
        file_path = _dashboard_asset_path(asset)
        if not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, media_type=content_type, headers={"Cache-Control": CACHE_CONTROL})

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def index():
        return _serve_static("index.html", "text/html; charset=utf-8")

    @app.get("/style.css", include_in_schema=False)
    def style_css():
        return _serve_static("style.css", "text/css; charset=utf-8")

    @app.get("/app.js", include_in_schema=False)
    def app_js():
        return _serve_static("app.js", "application/javascript; charset=utf-8")

    @app.get("/applications/{request_path:path}", include_in_schema=False)
    def serve_application_pdf(request_path: str):
        file_path = _application_pdf_path("/applications/" + request_path)
        if not file_path:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(file_path, media_type="application/pdf", headers={"Cache-Control": CACHE_CONTROL})

    for api_router in ALL_ROUTERS:
        app.include_router(api_router)

    return app


app = create_app()
