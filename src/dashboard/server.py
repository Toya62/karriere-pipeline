#!/usr/bin/env python3
"""FastAPI dashboard server for the Karriere Pipeline.

The HTTP surface (endpoints and JSON payloads) is unchanged from the previous
standard-library adapter, but it is now served by FastAPI/uvicorn. The JSON API
lives in :mod:`src.dashboard.routers`; the app factory and CORS/static wiring
live in :mod:`src.dashboard.app`.

Run with::

    python main.py dashboard [--port 8000] [--reload]

Module-level re-exports below keep the historical ``src.dashboard.server``
import surface working for the CLI and tests.
"""

import os
import sys

import uvicorn

from src.core.logger import get_logger
from src.dashboard.app import (
    _application_pdf_path,
    _cors_origin_header,
    _dashboard_asset_path,
    _dashboard_build_dir,
    _is_origin_allowed,
    app,
    create_app,
)
from src.dashboard.applications import (
    register_application_in_crm as _register_application_in_crm,
)
from src.dashboard.crm import (
    UNSET as _UNSET,
)
from src.dashboard.crm import (
    clean_cell as _clean_cell,
)
from src.dashboard.crm import (
    load_tracker_df as _load_tracker_df,
)
from src.dashboard.crm import (
    resolve_job_id as _resolve_job_id,
)
from src.dashboard.crm import (
    save_tracker_df as _save_tracker_df,
)
from src.dashboard.crm import (
    upsert_tracker_row as _upsert_tracker_row,
)
from src.dashboard.dismissals import (
    add_to_dismissed as _add_to_dismissed,
)
from src.dashboard.dismissals import (
    load_dismissed_df as _load_dismissed_df,
)
from src.dashboard.dismissals import (
    sync_dismissals_from_json,
)
from src.dashboard.git_ops import (
    GIT_LOCK as _GIT_LOCK,
)
from src.dashboard.git_ops import (
    _git_dir,
    git_sync_async,
)
from src.dashboard.git_ops import (
    git_current_branch as _git_current_branch,
)
from src.dashboard.git_ops import (
    git_in_progress as _git_in_progress,
)
from src.dashboard.git_ops import (
    git_root as _git_root,
)
from src.dashboard.git_ops import (
    git_sync as _git_sync,
)
from src.dashboard.git_ops import (
    safe_pull_rebase as _safe_pull_rebase,
)
from src.dashboard.state import (
    APP_GEN_STATUS as _APP_GEN_STATUS,
)
from src.dashboard.state import (
    CACHE as _CACHE,
)
from src.dashboard.state import (
    CACHE_TTL_SECONDS,
    DEFAULT_HOST,
)
from src.dashboard.state import (
    DESC_CACHE as _DESC_CACHE,
)
from src.dashboard.state import (
    SCRAPER_STATUS as _SCRAPER_STATUS,
)
from src.dashboard.state import (
    set_desc_cache as _set_desc_cache,
)
from src.dashboard.state import (
    set_gen_status as _set_gen_status,
)

logger = get_logger(__name__)

__all__ = [
    "CACHE_TTL_SECONDS",
    "DEFAULT_HOST",
    "_APP_GEN_STATUS",
    "_CACHE",
    "_DESC_CACHE",
    "_GIT_LOCK",
    "_SCRAPER_STATUS",
    "_UNSET",
    "_add_to_dismissed",
    "_application_pdf_path",
    "_clean_cell",
    "_cors_origin_header",
    "_dashboard_asset_path",
    "_dashboard_build_dir",
    "_git_current_branch",
    "_git_dir",
    "_git_in_progress",
    "_git_root",
    "_git_sync",
    "_is_origin_allowed",
    "_load_dismissed_df",
    "_load_tracker_df",
    "_register_application_in_crm",
    "_resolve_job_id",
    "_safe_pull_rebase",
    "_save_tracker_df",
    "_set_desc_cache",
    "_set_gen_status",
    "_upsert_tracker_row",
    "app",
    "create_app",
    "git_sync_async",
    "logger",
    "run",
    "sync_dismissals_from_json",
    "sys",
]


def run(port: int = 8000, host: str = DEFAULT_HOST) -> None:
    """Serve the dashboard with uvicorn until interrupted."""
    os.makedirs('dashboard', exist_ok=True)
    logger.info("\n==================================================")
    logger.info("  Karriere Pipeline Dashboard Server Started")
    logger.info(f"  Url: http://localhost:{port}")
    logger.info("  Press Ctrl+C to stop the server.")
    logger.info("==================================================\n")
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        logger.info("\nStopping dashboard server...")


if __name__ == '__main__':
    run()
