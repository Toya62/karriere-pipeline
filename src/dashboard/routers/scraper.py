"""Scraper control endpoints: status, logs, start, and stop."""

import os
import subprocess
import sys
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from src.core.logger import get_logger
from src.dashboard import state
from src.dashboard.git_ops import git_root, reap_zombies
from src.dashboard.routers.auth import get_current_user
from src.dashboard.schemas import MatcherRunRequest, ScraperRunRequest
from src.db.database import (
    create_scraper_run,
    get_user_profile,
    get_user_scraper_runs,
    update_scraper_run,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["scraper"])


def _user_log_path(user_id: int, log_name: str) -> str:
    """Return user-scoped log file path in data/logs/{user_id}/."""
    if user_id <= 0:
        return ""
    log_dir = os.path.join('data', 'logs', str(user_id))
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, log_name)


def _scraper_log_path() -> str:
    log_path = os.path.join('data', 'scraper_run.log')
    if not os.path.exists(log_path):
        log_path = os.path.join(git_root(), 'data', 'scraper_run.log')
    return log_path


def _matcher_log_path() -> str:
    log_path = os.path.join('data', 'matcher_run.log')
    if not os.path.exists(log_path):
        log_path = os.path.join(git_root(), 'data', 'matcher_run.log')
    return log_path


@router.get("/scraper-status")
@router.get("/scraper/status", include_in_schema=False)
def scraper_status(current_user: dict[str, Any] = Depends(get_current_user)):
    """Report whether the scraper subprocess is running for current user."""
    user_id = current_user.get("id", 0)
    if user_id <= 0:
        return {"running": False, "exit_code": None, "guest": True}

    is_running = False
    exit_code = None
    proc = state.SCRAPER_PROCESS
    if proc is not None:
        poll = proc.poll()
        if poll is None:
            is_running = True
        else:
            exit_code = poll
            state.CACHE["jobs"] = {}
            state.SCRAPER_PROCESS = None
    return {"running": is_running, "exit_code": exit_code, "guest": False}


@router.get("/scraper-logs")
@router.get("/scraper/logs", include_in_schema=False)
def scraper_logs(
    current_user: dict[str, Any] = Depends(get_current_user),
    system: bool = Query(False),
):
    """Return the tail of the scraper log scoped to current user. Zero server logs for guests."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"

    # Guest user: Zero server stdout exposure
    if user_id <= 0:
        return {"success": True, "logs": "", "total_lines": 0, "guest": True}

    # Admin system fallback if explicitly requested
    if is_admin and system:
        log_path = _scraper_log_path()
    else:
        log_path = _user_log_path(user_id, "scraper.log")

    if not log_path or not os.path.exists(log_path):
        return {
            "success": True,
            "logs": "No runs recorded yet for your account. Click 'Run Pipeline Discovery' to start.",
            "total_lines": 0,
            "guest": False,
        }

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_lines = "".join(lines[-300:])
        return {"success": True, "logs": last_lines, "total_lines": len(lines), "guest": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matcher-status")
@router.get("/matcher/status", include_in_schema=False)
def matcher_status(current_user: dict[str, Any] = Depends(get_current_user)):
    """Report whether the AI matcher subprocess is running for current user."""
    user_id = current_user.get("id", 0)
    if user_id <= 0:
        return {"running": False, "exit_code": None, "guest": True}

    is_running = False
    exit_code = None
    proc = state.MATCHER_PROCESS
    if proc is not None:
        poll = proc.poll()
        if poll is None:
            is_running = True
        else:
            exit_code = poll
            state.CACHE["jobs"] = {}
            state.MATCHER_PROCESS = None
    return {"running": is_running, "exit_code": exit_code, "guest": False}


@router.get("/matcher-logs")
@router.get("/matcher/logs", include_in_schema=False)
def matcher_logs(
    current_user: dict[str, Any] = Depends(get_current_user),
    system: bool = Query(False),
):
    """Return the tail of the AI matcher log scoped to current user. Zero server logs for guests."""
    user_id = current_user.get("id", 0)
    is_admin = current_user.get("role") == "admin"

    # Guest user: Zero server stdout exposure
    if user_id <= 0:
        return {"success": True, "logs": "", "total_lines": 0, "guest": True}

    if is_admin and system:
        log_path = _matcher_log_path()
    else:
        log_path = _user_log_path(user_id, "matcher.log")

    if not log_path or not os.path.exists(log_path):
        return {
            "success": True,
            "logs": "No AI evaluation runs recorded yet for your account.",
            "total_lines": 0,
            "guest": False,
        }

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_lines = "".join(lines[-300:])
        return {"success": True, "logs": last_lines, "total_lines": len(lines), "guest": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger-github-scraper")
@router.post("/run-scraper")
def run_scraper(
    body: ScraperRunRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Spawn the scraper subprocess scoped to current user."""
    user_id = current_user.get("id", 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required to run scrapers. Please sign in or register.")

    portal = (body.portal or "all").lower()
    days = str(body.days)

    try:
        if state.SCRAPER_PROCESS is not None and state.SCRAPER_PROCESS.poll() is None:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "A scraper process is already running. Please wait or stop it first.",
                },
            )

        root_dir = git_root()
        venv_python = os.path.abspath(os.path.join(root_dir, '.venv', 'bin', 'python'))
        python_bin = venv_python if os.path.exists(venv_python) else sys.executable

        user_profile = get_user_profile(user_id) or {}
        target_titles = user_profile.get("target_titles") or user_profile.get("job_search_preferences", {}).get("titles", [])
        queries_str = ", ".join(target_titles) if target_titles else ""

        run_id = create_scraper_run(
            user_id=user_id,
            portal=portal,
            days=int(days) if days.isdigit() else 1,
            queries=queries_str,
        )

        cmd = [python_bin, 'main.py', 'scrape', '--portal', portal, '--days', days, '--user-id', str(user_id)]

        reap_zombies()
        logger.info(f"Launching scraper for user {user_id}: {' '.join(cmd)}")
        log_path = _user_log_path(user_id, "scraper.log")
        log_file = open(log_path, 'w', encoding='utf-8')
        state.SCRAPER_PROCESS = subprocess.Popen(
            cmd,
            cwd=root_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        state.CACHE["jobs"] = {}
        return {
            "success": True,
            "mode": "local",
            "run_id": run_id,
            "message": f"⚡ Discovery pipeline started for {portal.upper()} ({days}d).",
            "log_path": log_path,
        }
    except Exception as e:
        logger.error(f"Failed to start local scraper: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scraper/runs")
def list_scraper_runs(current_user: dict[str, Any] = Depends(get_current_user)):
    """Fetch run history for current authenticated user."""
    user_id = current_user.get("id", 0)
    if user_id <= 0:
        return {"runs": []}
    return {"runs": get_user_scraper_runs(user_id)}


@router.post("/stop-scraper")
def stop_scraper():
    """Terminate the running scraper subprocess, if any."""
    proc = state.SCRAPER_PROCESS
    if proc and proc.poll() is None:
        try:
            proc.kill()
            state.SCRAPER_PROCESS = None
            state.SCRAPER_STATUS["running"] = False
            state.SCRAPER_STATUS["message"] = "Scraper stopped by user."
            state.SCRAPER_STATUS["error"] = "Terminated by user."
            return {"success": True, "message": "Scraper process terminated."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    state.SCRAPER_STATUS["running"] = False
    return {"success": True, "message": "No active scraper process running."}


@router.post("/stop-matcher")
def stop_matcher():
    """Terminate the running AI matcher subprocess, if any."""
    proc = state.MATCHER_PROCESS
    if proc and proc.poll() is None:
        try:
            proc.kill()
            state.MATCHER_PROCESS = None
            state.MATCHER_STATUS["running"] = False
            state.MATCHER_STATUS["message"] = "AI Matcher stopped by user."
            state.MATCHER_STATUS["error"] = "Terminated by user."
            return {"success": True, "message": "AI Matcher process terminated."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    state.MATCHER_STATUS["running"] = False
    return {"success": True, "message": "No active AI matcher process running."}


@router.post("/run-matcher")
def run_matcher(body: MatcherRunRequest = None):
    """Spawn the local AI matcher subprocess with independent log."""
    max_age = str(body.max_age_days if body and body.max_age_days is not None else 2)
    portal = body.portal if body and body.portal else None

    try:
        if state.MATCHER_PROCESS is not None and state.MATCHER_PROCESS.poll() is None:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "An AI matcher process is already running. Please wait or stop it first.",
                },
            )

        root_dir = git_root()
        venv_python = os.path.abspath(os.path.join(root_dir, '.venv', 'bin', 'python'))
        python_bin = venv_python if os.path.exists(venv_python) else sys.executable
        cmd = [python_bin, 'main.py', 'match', '--max-age-days', max_age]
        if portal and portal.lower() != "all":
            cmd.extend(['--portal', portal.lower()])

        reap_zombies()
        logger.info(f"Launching AI matcher: {' '.join(cmd)}")
        log_path = os.path.join(root_dir, 'data', 'matcher_run.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_file = open(log_path, 'w', encoding='utf-8')
        state.MATCHER_PROCESS = subprocess.Popen(
            cmd,
            cwd=root_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        state.CACHE["jobs"] = {}
        return {
            "success": True,
            "mode": "local",
            "message": f"⚡ AI Matcher started for last {max_age} days.",
            "log_path": log_path,
        }
    except Exception as e:
        logger.error(f"Failed to start AI matcher: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending-matches")
def get_pending_matches(max_age_days: int = 2):
    """Return count of recent pending jobs that need AI evaluation."""
    from datetime import datetime, timedelta
    from src.core.utils import GERMAN_TZ
    from src.db.database import get_db_connection

    try:
        conn = get_db_connection()
        cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM jobs j
            LEFT JOIN evaluations e ON j.id = e.job_id
            WHERE e.id IS NULL AND length(j.description) > 30
            AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
            """,
            (cutoff,),
        )
        row = cursor.fetchone()
        pending = row[0] if row else 0
        conn.close()
        return {"pending_count": pending, "max_age_days": max_age_days}
    except Exception as e:
        logger.error(f"Failed to fetch pending matches count: {e}")
        return {"pending_count": 0, "max_age_days": max_age_days, "error": str(e)}
