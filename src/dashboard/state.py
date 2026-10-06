"""Shared runtime state for the dashboard API.

Caches, the scraper subprocess handle, and application-generation status live
here so every router observes the same objects. Importing this module never
pulls in the HTTP app, keeping the data layers usable and testable on their own.

The scraper process handle is deliberately accessed as a module attribute
(``state.SCRAPER_PROCESS``) rather than copied into routers, so rebinding it
from a request handler or a test is visible everywhere.
"""

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
