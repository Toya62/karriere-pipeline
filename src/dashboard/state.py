"""Shared runtime state for the dashboard API.

Caches, the scraper subprocess handle, and application-generation status live
here so every router observes the same objects. Importing this module never
pulls in the HTTP app, keeping the data layers usable and testable on their own.

The scraper process handle is deliberately accessed as a module attribute
(``state.SCRAPER_PROCESS``) rather than copied into routers, so rebinding it
from a request handler or a test is visible everywhere.
"""

from typing import Any

DEFAULT_HOST = "127.0.0.1"
CACHE_TTL_SECONDS = 60  # Cache duration: 1 minute

#: Map: filename -> {"data": list of dicts, "time": float}; "tracker" -> same shape.
CACHE: dict = {"jobs": {}, "tracker": None, "last_sync": 0}
#: Map: job_url -> description string (bounded, oldest evicted first).
DESC_CACHE: dict = {}
#: Map: task_key -> {"status": "running"|"complete"|"error", ...} (bounded).
APP_GEN_STATUS: dict = {}
#: Current scraper subprocess bookkeeping.
SCRAPER_STATUS: dict = {"running": False, "message": "Idle", "error": None}
#: The live scraper :class:`subprocess.Popen` handle, or ``None``.
SCRAPER_PROCESS = None
#: Current scraper run ID tracked in database
CURRENT_SCRAPER_RUN_ID: int | None = None
#: Current AI matcher subprocess bookkeeping.
MATCHER_STATUS: dict = {"running": False, "message": "Idle", "error": None}
#: The live matcher :class:`subprocess.Popen` handle, or ``None``.
MATCHER_PROCESS = None

# Multi-tenant process bookkeeping maps: user_id -> Popen / status
USER_SCRAPER_PROCESSES: dict[int, Any] = {}
USER_MATCHER_PROCESSES: dict[int, Any] = {}
USER_SCRAPER_STATUS: dict[int, dict] = {}
USER_MATCHER_STATUS: dict[int, dict] = {}
USER_SCRAPER_RUN_IDS: dict[int, int | None] = {}


def get_user_scraper_run_id(user_id: int) -> int | None:
    """Retrieve active scraper run ID for user."""
    run_id = USER_SCRAPER_RUN_IDS.get(user_id)
    if run_id is None and (user_id <= 1 or user_id == 0):
        return CURRENT_SCRAPER_RUN_ID
    return run_id


def set_user_scraper_run_id(user_id: int, run_id: int | None):
    """Register active scraper run ID for user."""
    global CURRENT_SCRAPER_RUN_ID
    USER_SCRAPER_RUN_IDS[user_id] = run_id
    if user_id <= 1 or user_id == 0:
        CURRENT_SCRAPER_RUN_ID = run_id


def get_user_scraper_process(user_id: int):
    """Retrieve active scraper subprocess for user (falls back to legacy singleton for user 1)."""
    proc = USER_SCRAPER_PROCESSES.get(user_id)
    if proc is None and (user_id <= 1 or user_id == 0):
        proc = SCRAPER_PROCESS
    return proc


def set_user_scraper_process(user_id: int, proc):
    """Register active scraper subprocess for user."""
    global SCRAPER_PROCESS
    USER_SCRAPER_PROCESSES[user_id] = proc
    if user_id <= 1 or user_id == 0:
        SCRAPER_PROCESS = proc


def get_user_matcher_process(user_id: int):
    """Retrieve active matcher subprocess for user."""
    proc = USER_MATCHER_PROCESSES.get(user_id)
    if proc is None and (user_id <= 1 or user_id == 0):
        proc = MATCHER_PROCESS
    return proc


def set_user_matcher_process(user_id: int, proc):
    """Register active matcher subprocess for user."""
    global MATCHER_PROCESS
    USER_MATCHER_PROCESSES[user_id] = proc
    if user_id <= 1 or user_id == 0:
        MATCHER_PROCESS = proc


def set_desc_cache(url: str, desc: str) -> None:
    """Store in description cache with LRU size limit."""
    if len(DESC_CACHE) >= 1000:
        for k in list(DESC_CACHE.keys())[:200]:
            DESC_CACHE.pop(k, None)
    DESC_CACHE[url] = desc


def set_gen_status(key: str, status: dict) -> None:
    """Store generation status with bounded cache size."""
    if len(APP_GEN_STATUS) >= 200:
        for k in list(APP_GEN_STATUS.keys())[:50]:
            APP_GEN_STATUS.pop(k, None)
    APP_GEN_STATUS[key] = status


def clear_data_caches() -> None:
    """Invalidate the job and tracker caches after a write or sync."""
    CACHE["jobs"] = {}
    CACHE["tracker"] = None
