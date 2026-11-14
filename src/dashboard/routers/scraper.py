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
    if os.path.exists(log_path):
        return log_path
    fallback = os.path.join(git_root(), 'data', 'scraper_run.log')
    if os.path.exists(fallback):
        return fallback
    return log_path


def _matcher_log_path() -> str:
    log_path = os.path.join('data', 'matcher_run.log')
    if os.path.exists(log_path):
        return log_path
    fallback = os.path.join(git_root(), 'data', 'matcher_run.log')
    if os.path.exists(fallback):
        return fallback
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
    proc = state.get_user_scraper_process(user_id)
    if proc is not None:
        poll = proc.poll()
        if poll is None:
            is_running = True
        else:
            exit_code = poll
            state.CACHE["jobs"] = {}
            state.set_user_scraper_process(user_id, None)
            run_id = state.get_user_scraper_run_id(user_id)
            if run_id:
                try:
                    if exit_code != 0:
                        update_scraper_run(
                            run_id,
                            status="failed",
                            error_message=f"Process exited with code {exit_code}",
                        )
                except Exception as e:
                    logger.warning(f"Failed to update scraper run #{run_id}: {e}")
                finally:
                    state.set_user_scraper_run_id(user_id, None)
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

    # Admin system fallback if explicitly requested or if user log doesn't exist
    user_log = _user_log_path(user_id, "scraper.log")
    if is_admin and (system or not os.path.exists(user_log)):
        log_path = _scraper_log_path()
    else:
        log_path = user_log

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
    proc = state.get_user_matcher_process(user_id)
    if proc is not None:
        poll = proc.poll()
        if poll is None:
            is_running = True
        else:
            exit_code = poll
            state.CACHE["jobs"] = {}
            state.set_user_matcher_process(user_id, None)
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

    user_log = _user_log_path(user_id, "matcher.log")
    if is_admin and (system or not os.path.exists(user_log)):
        log_path = _matcher_log_path()
    else:
        log_path = user_log

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


def _is_multi_user_mode() -> bool:
    """True when the deployment runs multi-tenant (same rule as main.py)."""
    return os.environ.get("MULTI_USER_MODE", "").strip().lower() in ("1", "true", "yes", "on") or os.environ.get(
        "ENV", ""
    ).strip().lower() in ("production", "prod")


ALLOWED_PORTALS = {
    "all", "linkedin", "indeed", "xing", "bund", "ba",
    "personio", "ashby", "greenhouse", "arbeitnow"
}


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

    portal = (body.portal or "all").lower().strip()
    if portal not in ALLOWED_PORTALS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Invalid portal '{portal}'. Must be one of: {', '.join(sorted(ALLOWED_PORTALS))}",
            },
        )

    try:
        days_int = int(body.days) if body and body.days is not None else 1
        if not (1 <= days_int <= 30):
            raise ValueError()
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Days must be an integer between 1 and 30."},
        )
    days = str(days_int)

    from src.core.entitlements import check_feature_entitlement, check_rate_limit, record_usage

    # 1. Tier Portal Restriction Check
    if portal != "all":
        entitled, reason = check_feature_entitlement(current_user, f"portal:{portal}")
        if not entitled:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "tier_restricted",
                    "tier": current_user.get("tier", "free"),
                    "message": reason,
                    "upgrade_url": "/upgrade",
                },
            )

    # 2. Daily Scraper Runs Quota
    has_quota, quota_msg, quota_stats = check_rate_limit(current_user, "scraper_runs", increment=1)
    if not has_quota:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "tier_limit_reached",
                "tier": current_user.get("tier", "free"),
                "message": quota_msg,
                "stats": quota_stats,
                "upgrade_url": "/upgrade",
            },
        )

    try:
        active_proc = state.get_user_scraper_process(user_id)
        if active_proc is not None and active_proc.poll() is None:
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
        from src.scrapers.query_builder import get_candidate_eligible_portals
        eligible_portals = get_candidate_eligible_portals(user_profile)
        if portal != "all" and portal not in eligible_portals:
            target_countries = user_profile.get("job_search_preferences", {}).get("countries", ["Germany"])
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Portal '{portal}' is not eligible for candidate target region ({', '.join(target_countries)}). Eligible portals: {', '.join(eligible_portals)}",
                },
            )

        target_titles = user_profile.get("target_titles") or user_profile.get("job_search_preferences", {}).get("titles", [])
        queries_str = ", ".join(target_titles) if target_titles else ""

        run_id = create_scraper_run(
            user_id=user_id,
            portal=portal,
            days=int(days) if days.isdigit() else 1,
            queries=queries_str,
        )

        cmd = [python_bin, 'main.py', 'scrape', '--portal', portal, '--days', days, '--user-id', str(user_id)]
        if not getattr(body, "auto_match", True):
            cmd.append('--no-match')
        if run_id:
            cmd.extend(['--run-id', str(run_id)])

        reap_zombies()
        logger.info(f"Launching scraper for user {user_id}: {' '.join(cmd)}")
        log_path = _user_log_path(user_id, "scraper.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_file = open(log_path, 'w', encoding='utf-8')
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=root_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            state.set_user_scraper_process(user_id, proc)
            state.set_user_scraper_run_id(user_id, run_id)
            record_usage(user_id, "scraper_runs", 1)
        except Exception as proc_err:
            log_file.close()
            raise proc_err
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


@router.get("/scraper/sources")
def get_scraper_sources(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return real status, last ingestion timestamp, and total jobs count for all portal sources."""
    user_id = current_user.get("id", 0)
    profile = get_user_profile(user_id) if user_id > 0 else None

    from src.scrapers.query_builder import get_candidate_eligible_portals
    from src.db.database import get_db_connection

    eligible = set(get_candidate_eligible_portals(profile))

    portal_stats: dict[str, dict[str, Any]] = {}
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT portal, COUNT(*), MAX(scraped_at) FROM jobs WHERE portal IS NOT NULL GROUP BY portal;")
        for row in cur.fetchall():
            portal_key = (row[0] or "").lower().strip()
            portal_stats[portal_key] = {
                "jobs_count": int(row[1]),
                "last_scraped_at": str(row[2]) if row[2] else None,
            }
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to query portal stats: {e}")

    portal_definitions = [
        {"id": "ba", "name": "Bundesagentur für Arbeit (BA)", "type": "API / Scraper"},
        {"id": "linkedin", "name": "LinkedIn Jobs", "type": "Headless Session"},
        {"id": "indeed", "name": "Indeed Germany", "type": "Scraper"},
        {"id": "bund", "name": "Bund.de / Interamt", "type": "Public Portal"},
        {"id": "xing", "name": "XING Jobs", "type": "API Feed"},
        {"id": "arbeitnow", "name": "Arbeitnow", "type": "REST API"},
        {"id": "personio", "name": "Personio ATS", "type": "ATS Scraper"},
        {"id": "ashby", "name": "AshbyHQ ATS", "type": "ATS Scraper"},
        {"id": "greenhouse", "name": "Greenhouse ATS", "type": "ATS Scraper"},
    ]

    sources = []
    for p in portal_definitions:
        pid = p["id"]
        stats = portal_stats.get(pid, {"jobs_count": 0, "last_scraped_at": None})
        is_eligible = pid in eligible
        status = "Active" if is_eligible else "Inactive (Region Filter)"
        sources.append({
            "id": pid,
            "name": p["name"],
            "type": p["type"],
            "status": status,
            "eligible": is_eligible,
            "jobs_count": stats["jobs_count"],
            "last_scraped_at": stats["last_scraped_at"],
        })

    return {"sources": sources}


@router.post("/stop-scraper")
def stop_scraper(current_user: dict[str, Any] = Depends(get_current_user)):
    """Terminate the running scraper subprocess for current user."""
    user_id = current_user.get("id", 0)
    proc = state.get_user_scraper_process(user_id)
    if proc and proc.poll() is None:
        try:
            proc.kill()
            state.set_user_scraper_process(user_id, None)
            run_id = state.get_user_scraper_run_id(user_id)
            if run_id:
                try:
                    update_scraper_run(
                        run_id,
                        status="stopped",
                        error_message="Terminated by user",
                    )
                except Exception:
                    pass
                finally:
                    state.set_user_scraper_run_id(user_id, None)
            state.SCRAPER_STATUS["running"] = False
            state.SCRAPER_STATUS["message"] = "Scraper stopped by user."
            state.SCRAPER_STATUS["error"] = "Terminated by user."
            return {"success": True, "message": "Scraper process terminated."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    state.SCRAPER_STATUS["running"] = False
    return {"success": True, "message": "No active scraper process running."}


@router.post("/stop-matcher")
def stop_matcher(current_user: dict[str, Any] = Depends(get_current_user)):
    """Terminate the running AI matcher subprocess for current user."""
    user_id = current_user.get("id", 0)
    proc = state.get_user_matcher_process(user_id)
    if proc and proc.poll() is None:
        try:
            proc.kill()
            state.set_user_matcher_process(user_id, None)
            state.MATCHER_STATUS["running"] = False
            state.MATCHER_STATUS["message"] = "AI Matcher stopped by user."
            state.MATCHER_STATUS["error"] = "Terminated by user."
            return {"success": True, "message": "AI Matcher process terminated."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    state.MATCHER_STATUS["running"] = False
    return {"success": True, "message": "No active AI matcher process running."}


@router.post("/run-matcher")
def run_matcher(
    body: MatcherRunRequest = None,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Spawn the local AI matcher subprocess with independent log and tier quota gating."""
    user_id = current_user.get("id", 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required to run AI matcher. Please sign in or register.")

    from src.core.entitlements import check_rate_limit, record_usage

    # Quota check for monthly AI evaluations (Free: 25/mo, Pro: unlimited)
    has_quota, quota_msg, quota_stats = check_rate_limit(current_user, "ai_evaluations", increment=1)
    if not has_quota:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "tier_limit_reached",
                "tier": current_user.get("tier", "free"),
                "message": quota_msg,
                "stats": quota_stats,
                "upgrade_url": "/upgrade",
            },
        )

    try:
        max_age_int = int(body.max_age_days) if body and body.max_age_days is not None else 7  # default matches config.AUTO_MATCH_MAX_AGE_DAYS (claim 12)
        if not (1 <= max_age_int <= 30):
            raise ValueError()
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "max_age_days must be an integer between 1 and 30."},
        )
    max_age = str(max_age_int)

    portal = (body.portal or "").lower().strip() if body and body.portal else None
    if portal and portal != "all" and portal not in ALLOWED_PORTALS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Invalid portal '{portal}'. Must be one of: {', '.join(sorted(ALLOWED_PORTALS))}",
            },
        )

    try:
        active_proc = state.get_user_matcher_process(user_id)
        if active_proc is not None and active_proc.poll() is None:
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
        if user_id > 0:
            cmd.extend(['--user-id', str(user_id)])
        if portal and portal.lower() != "all":
            cmd.extend(['--portal', portal.lower()])

        reap_zombies()
        logger.info(f"Launching AI matcher: {' '.join(cmd)}")
        log_path = _user_log_path(user_id, "matcher.log") if user_id > 0 else os.path.join(root_dir, 'data', 'matcher_run.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_file = open(log_path, 'w', encoding='utf-8')
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=root_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            state.set_user_matcher_process(user_id, proc)
            # Consume 1 evaluation run against user's monthly quota only after successful process spawn
            record_usage(user_id, "ai_evaluations", amount=1)
        except Exception as proc_err:
            log_file.close()
            raise proc_err
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
def get_pending_matches(
    max_age_days: int = 7,  # matches config.AUTO_MATCH_MAX_AGE_DAYS (claim 12)
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Return count of recent pending jobs that need AI evaluation."""
    from datetime import datetime, timedelta
    from src.core.utils import GERMAN_TZ
    from src.db.database import get_db_connection

    user_id = current_user.get("id", 0)

    # Guests have no tenant scope: no count. (Previously a guest got the
    # global pending count via the legacy evaluations table.)
    if user_id <= 0:
        return {"pending_count": 0, "max_age_days": max_age_days}
    if not (1 <= max_age_days <= 30):
        raise HTTPException(status_code=400, detail="max_age_days must be an integer between 1 and 30.")

    conn = None
    try:
        conn = get_db_connection()
        cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.cursor()
        if _is_multi_user_mode():
            # Tenant-scoped for every authenticated user, including admin
            # (id 1). The old `user_id > 1` branch sent the admin down the
            # unscoped legacy path (F15 class).
            cursor.execute(
                """
                SELECT COUNT(*) FROM jobs j
                LEFT JOIN user_jobs uj ON j.id = uj.job_id AND uj.user_id = ?
                WHERE uj.id IS NULL AND length(j.description) > 30
                AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
                """,
                (user_id, cutoff),
            )
        else:
            # Single-user mode keeps the legacy evaluations table.
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
        return {"pending_count": pending, "max_age_days": max_age_days}
    except Exception as e:
        logger.error(f"Failed to fetch pending matches count: {e}")
        return {"pending_count": 0, "max_age_days": max_age_days, "error": str(e)}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
