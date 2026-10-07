"""Git synchronization endpoints for the dashboard."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.logger import get_logger
from src.dashboard.git_ops import git_root, safe_pull_rebase
from src.dashboard.state import CACHE

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["sync"])


@router.get("/pull")
@router.get("/sync")
def pull_and_sync():
    """Pull ``origin/main`` and ingest new jobs into SQLite."""
    root_dir = git_root()
    try:
        ok, detail = safe_pull_rebase(root_dir)

        # Automatically ingest newly pulled jobs and evaluations into SQLite.
        try:
            from src.db import sync_remote_git_db
            sync_remote_git_db()
        except Exception as sync_err:
            logger.warning(f"Database sync after git pull encountered warning: {sync_err}")

        CACHE["jobs"].clear()
        return {
            "success": True,
            "message": ("Successfully synchronized with GitHub origin/main and updated SQLite database!"
                        if ok else f"Sync skipped: {detail}"),
            "output": detail,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
