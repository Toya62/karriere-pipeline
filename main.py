#!/usr/bin/env python3
"""
main.py  —  Unified CLI command center for Karriere Pipeline.
Allows running scrapers with automatic AI matching, or starting the dashboard.

Usage:
    python main.py scrape [--portal PORTAL] [--days DAYS] [--no-match]
    python main.py match [--file CSV] [--limit N]
    python main.py dashboard [--port PORT]
    python main.py pull
    python main.py compile [--keep-tex] [--no-push]
"""

import argparse
import atexit
import inspect
import json
import os
import sys
from contextlib import closing

try:
    import fcntl  # Unix-only; lockfile disabled on platforms without it (F6)
except ImportError:  # pragma: no cover - Windows
    fcntl = None

# Define the absolute import source
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Auto-switch to project virtualenv if running outside .venv as main script
if __name__ == "__main__":
    _venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "bin", "python"))
    if os.path.exists(_venv_python) and os.path.realpath(sys.executable) != os.path.realpath(_venv_python):
        os.execv(_venv_python, [_venv_python] + sys.argv)

from src.scraper import (
    run_scrape_linkedin, run_scrape_indeed, run_scrape_ba,
    run_scrape_bund, run_scrape_xing, run_scrape_personio,
    run_scrape_arbeitnow, run_scrape_ashby, run_scrape_greenhouse
)
from src.dashboard.server import DEFAULT_HOST, run as run_server
from src.config import get_window_tag
from src.ai.matcher import run_gemini_matcher
from src.db.database import get_user_profile
from src.scrapers.query_builder import build_portal_queries

# ── Audit 2026-11-11 helpers ──────────────────────────────────────────────

def _is_multi_user_mode() -> bool:
    """True when the deployment is a multi-user SaaS instance (F8/F15).

    Canonical switch is MULTI_USER_MODE (documented in .env.example); the
    production ENV value is accepted as a fallback, matching
    src/core/security.py.
    """
    if os.environ.get("MULTI_USER_MODE", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return os.environ.get("ENV", "").strip().lower() in ("production", "prod")


def _require_user_id_in_multi_user(user_id, where: str) -> None:
    """Fail loudly instead of evaluating jobs globally in multi-user mode (F15)."""
    if _is_multi_user_mode() and user_id is None:
        raise ValueError(
            f"user_id is required in multi-user mode ({where}); refusing to evaluate "
            "jobs globally. Pass --user-id (admin: 1)."
        )


def _get_auto_match_max_age_days() -> int:
    """Parse AUTO_MATCH_MAX_AGE_DAYS, failing fast on bad values (F16)."""
    from src.config import AUTO_MATCH_MAX_AGE_DAYS
    raw = os.environ.get("AUTO_MATCH_MAX_AGE_DAYS")
    if raw is None:
        return int(AUTO_MATCH_MAX_AGE_DAYS)
    try:
        val = int(str(raw).strip())
    except ValueError:
        raise ValueError(
            f"AUTO_MATCH_MAX_AGE_DAYS must be an integer number of days, got {raw!r}."
        )
    if val < 0 or val > 365:
        raise ValueError(
            f"AUTO_MATCH_MAX_AGE_DAYS must be between 0 and 365 days, got {val}."
        )
    return val


def _days_arg(value: str) -> int:
    """argparse type for --days: 1..30 (F16)."""
    try:
        val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--days must be an integer, got {value!r}.")
    if val < 1 or val > 30:
        raise argparse.ArgumentTypeError(f"--days must be between 1 and 30, got {val}.")
    return val


def _max_age_arg(value: str) -> int:
    """argparse type for --max-age-days: 0 (all history) .. 365 (F16)."""
    try:
        val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--max-age-days must be an integer, got {value!r}."
        )
    if val < 0 or val > 365:
        raise argparse.ArgumentTypeError(
            f"--max-age-days must be between 0 and 365, got {val}."
        )
    return val


def _alert_telegram(message: str) -> bool:
    """Send a Telegram alert; log delivery failures instead of swallowing them (F18)."""
    try:
        from src.core.notifier import send_telegram_alert
        delivered = send_telegram_alert(message)
        if not delivered:
            print(
                f"[Warning] Telegram alert was not delivered (send returned False): "
                f"{message[:160]}",
                file=sys.stderr,
            )
        return bool(delivered)
    except Exception as e:
        print(f"[Warning] Telegram alert failed with exception: {e}", file=sys.stderr)
        return False


_SCRAPE_LOCK_FP = None


def _acquire_scrape_lock() -> None:
    """Hold an flock on data/.scrape.lock so overlapping runs cannot stack (F6).

    The lock is held for the lifetime of the process (released via atexit).
    """
    global _SCRAPE_LOCK_FP
    if fcntl is None:
        return
    os.makedirs("data", exist_ok=True)
    _SCRAPE_LOCK_FP = open(os.path.join("data", ".scrape.lock"), "a+")
    try:
        fcntl.flock(_SCRAPE_LOCK_FP.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            "[ERROR] Another scrape run is already in progress "
            "(data/.scrape.lock is held). Aborting.",
            file=sys.stderr,
        )
        _SCRAPE_LOCK_FP.close()
        _SCRAPE_LOCK_FP = None
        sys.exit(1)


def _release_scrape_lock() -> None:
    global _SCRAPE_LOCK_FP
    if _SCRAPE_LOCK_FP is not None and fcntl is not None:
        try:
            fcntl.flock(_SCRAPE_LOCK_FP.fileno(), fcntl.LOCK_UN)
            _SCRAPE_LOCK_FP.close()
        except Exception:
            pass
        _SCRAPE_LOCK_FP = None


atexit.register(_release_scrape_lock)


def _invoke_scraper(scrape_func, scrape_kwargs: dict) -> None:
    """Call a scraper with exactly the kwargs its signature accepts (F4).

    The previous implementation probed the signature by catching TypeError,
    which also swallowed genuine TypeErrors raised *inside* the scraper and
    retried it with different arguments. Inspect the signature once instead;
    a real TypeError now propagates as a genuine scraper error.
    """
    try:
        sig = inspect.signature(scrape_func)
    except (TypeError, ValueError):
        scrape_func(**scrape_kwargs)
        return
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        scrape_func(**scrape_kwargs)
        return
    accepted = {k: v for k, v in scrape_kwargs.items() if k in params}
    required = [
        name
        for name, p in params.items()
        if p.default is inspect.Parameter.empty
        and p.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    # If a required argument is missing, the resulting TypeError is a real bug
    # and must surface — do not retry with a different call shape.
    scrape_func(**accepted)


# Portal slugs allowed in SQL filters, with their URL LIKE fragments as bound
# parameters. No portal string is ever interpolated into SQL (F3).
PORTAL_URL_PATTERNS = {
    "arbeitnow": ("j.url LIKE ?", ["%arbeitnow%"]),
    "linkedin": ("(j.url LIKE ? OR j.url LIKE ?)", ["%linkedin%", "%licdn%"]),
    "xing": ("j.url LIKE ?", ["%xing%"]),
    "personio": ("j.url LIKE ?", ["%personio%"]),
    "ashby": ("j.url LIKE ?", ["%ashbyhq%"]),
    "greenhouse": ("j.url LIKE ?", ["%greenhouse.io%"]),
    "bund": ("(j.url LIKE ? OR j.url LIKE ?)", ["%bund.de%", "%interamt.de%"]),
    "ba": ("j.url LIKE ?", ["%arbeitsagentur.de%"]),
    "indeed": ("j.url LIKE ?", ["%indeed%"]),
}
ALLOWED_PORTAL_SLUGS = frozenset(PORTAL_URL_PATTERNS)


def _check_ai_quota(user_id: int | None) -> bool:
    """Evaluate whether user has remaining AI evaluation quota (monthly_ai_evaluations).

    Quota is accounted per matcher *invocation* (one run/batch of pending jobs),
    not per individual job: each ``run_gemini_matcher_on_db`` call consumes one
    unit via ``record_usage(..., 1)``. This matches ``handle_match`` (one match
    run = one usage) and keeps the pipelined consumer loop consistent.

    Returns True in single-user/local mode (user_id is None) or when
    check_rate_limit passes; False when quota is exhausted. This is a read-only
    preview (check_rate_limit does not persist); the actual increment happens in
    record_usage after a successful matcher run.
    """
    if user_id is None:
        return True
    from src.db.database import get_user_by_id
    from src.core.entitlements import check_rate_limit
    user = get_user_by_id(int(user_id))
    has_quota, _, _ = check_rate_limit(user, "ai_evaluations", increment=1)
    return bool(has_quota)


def _run_portal_and_ai(
    portal_name: str,
    scrape_func,
    auto_ai: bool = True,
    queries: list = None,
    location: str | None = None,
    country_indeed: str | None = None,
    user_profile: dict | None = None,
    user_id: int | None = None,
) -> dict:
    """Executes a scraper for a portal, runs AI matching directly via SQLite, and returns run stats."""
    print(f"\n{'='*60}")
    print(f"  [1/2] 🌐 Scraping Portal: {portal_name.upper()}")
    print(f"{'='*60}\n")
    
    scraped_count = 0
    approved_count = 0
    db_path = "data/karriere.db"
    prev_max_id = 0

    from src.db.database import get_db_connection, is_postgres
    if is_postgres() or os.path.exists(db_path):
        try:
            # F5: closing() guarantees the connection returns to the pool /
            # closes even when execute() raises.
            with closing(get_db_connection(db_path)) as conn:
                row = conn.cursor().execute("SELECT COALESCE(MAX(id), 0) FROM jobs").fetchone()
            prev_max_id = row[0] if row else 0
        except Exception as e:
            print(f"[Warning] Failed to fetch prev_max_id: {e}", file=sys.stderr)

    scrape_kwargs = {}
    if queries:
        scrape_kwargs["queries"] = queries
    if location:
        scrape_kwargs["location"] = location
    if country_indeed:
        scrape_kwargs["country_indeed"] = country_indeed
    if user_profile:
        scrape_kwargs["user_profile"] = user_profile

    try:
        _invoke_scraper(scrape_func, scrape_kwargs)
    except Exception as e:
        print(f"[ERROR] Failed scraping {portal_name}: {e}", file=sys.stderr)
        _alert_telegram(
            f"⚠️ *Scraper Error on {portal_name}*\n\nError: {e}\nCheck GitHub Actions run logs for details."
        )
        return {"scraped": 0, "approved": 0, "error": str(e)}

    # Measure newly added jobs in Database
    if is_postgres() or os.path.exists(db_path):
        try:
            with closing(get_db_connection(db_path)) as conn:
                row = conn.cursor().execute("SELECT COUNT(*) FROM jobs WHERE id > ?", (prev_max_id,)).fetchone()
            scraped_count = row[0] if row else 0
        except Exception as e:
            print(f"[Warning] Failed to count new jobs: {e}", file=sys.stderr)

    if auto_ai:
        # Check for ANY pending unevaluated jobs for this portal in Database
        pending_count = 0
        # F15: in multi-user mode matching must be scoped to a user; a
        # missing user_id used to silently evaluate every user's jobs.
        _require_user_id_in_multi_user(user_id, "_run_portal_and_ai")
        # F16: parse once, failing fast on a malformed env value instead of
        # falling back silently inside the count query below.
        match_max_days = _get_auto_match_max_age_days()

        p_slug = portal_name.lower().strip()
        if "indeed" in p_slug: p_slug = "indeed"
        elif "linkedin" in p_slug: p_slug = "linkedin"
        elif "xing" in p_slug: p_slug = "xing"
        elif "bund" in p_slug or "interamt" in p_slug: p_slug = "bund"
        elif "ba" in p_slug or "agentur" in p_slug or "arbeitsagentur" in p_slug: p_slug = "ba"
        elif "personio" in p_slug: p_slug = "personio"
        elif "ashby" in p_slug: p_slug = "ashby"
        elif "greenhouse" in p_slug: p_slug = "greenhouse"
        elif "arbeitnow" in p_slug: p_slug = "arbeitnow"

        # F3: reject any slug outside the allowlist instead of interpolating
        # it into SQL; the URL LIKE patterns are bound parameters, never
        # string-interpolated.
        if p_slug not in ALLOWED_PORTAL_SLUGS:
            raise ValueError(
                f"Unknown portal slug {p_slug!r}; refusing to build the "
                "pending-jobs query. Allowed: " + ", ".join(sorted(ALLOWED_PORTAL_SLUGS))
            )
        url_sql, url_params = PORTAL_URL_PATTERNS[p_slug]
        id_cond = f"j.id > {int(prev_max_id)} OR " if prev_max_id > 0 else ""
        p_filter = f"AND ({id_cond}j.portal = ? OR {url_sql})"
        sql_params = [p_slug, *url_params]

        if is_postgres() or os.path.exists(db_path):
            try:
                from src.core.utils import GERMAN_TZ
                from datetime import datetime, timedelta
                cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=match_max_days)).strftime("%Y-%m-%d %H:%M:%S")
                if user_id is not None:
                    q_pending = """
                        SELECT COUNT(*) FROM jobs j
                        LEFT JOIN user_jobs uj ON j.id = uj.job_id AND uj.user_id = ?
                        WHERE uj.id IS NULL AND length(j.description) > 30 {p_filter}
                        AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
                    """.replace("{p_filter}", p_filter)
                    params = (*sql_params, user_id, cutoff)
                else:
                    q_pending = """
                        SELECT COUNT(*) FROM jobs j
                        LEFT JOIN evaluations e ON j.id = e.job_id
                        WHERE e.id IS NULL AND length(j.description) > 30 {p_filter}
                        AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
                    """.replace("{p_filter}", p_filter)
                    params = (*sql_params, cutoff)
                with closing(get_db_connection(db_path)) as conn:
                    row = conn.cursor().execute(q_pending, params).fetchone()
                pending_count = row[0] if row else 0
            except Exception as e:
                print(f"[Warning] Failed to count pending jobs: {e}", file=sys.stderr)
                pending_count = scraped_count

        db_label = "PostgreSQL" if is_postgres() else "SQLite"
        if pending_count > 0:
            if not _check_ai_quota(user_id):
                print(
                    f"[Quota Warning] AI evaluations quota exhausted for user {user_id}. "
                    f"Skipping matcher for {portal_name}.",
                    file=sys.stderr,
                )
                _alert_telegram(
                    f"⚠️ *AI Quota Exhausted on {portal_name}*\n\n"
                    f"Monthly AI evaluations quota reached. AI matcher skipped for this portal."
                )
                return {"scraped": scraped_count, "approved": 0, "quota_skipped": True}

            print(f"\n{'='*60}")
            print(f"  [2/2] 🤖 Evaluating {pending_count} Pending Jobs for {portal_name} via {db_label}")
            print(f"{'='*60}\n")
            try:
                from src.ai.matcher import run_gemini_matcher_on_db
                # Evaluate all pending jobs within recent window so no recent jobs are stranded
                approved_jobs = run_gemini_matcher_on_db(
                    db_path=db_path,
                    portal=portal_name,
                    min_job_id=None,
                    max_age_days=match_max_days,
                    user_id=user_id,
                    candidate_profile=user_profile,
                )
                approved_count = len(approved_jobs) if approved_jobs else 0
                if user_id:
                    from src.core.entitlements import record_usage
                    record_usage(int(user_id), "ai_evaluations", 1)
            except Exception as e:
                print(f"[ERROR] Matcher failed for {portal_name}: {e}", file=sys.stderr)
                _alert_telegram(f"⚠️ *AI Matcher Error on {portal_name}*\n\nError: {e}")
        else:
            print(f"\n[Info] All jobs for {portal_name} already evaluated; nothing pending.")

    return {"scraped": scraped_count, "approved": approved_count}

def _run_all_portals_pipelined(p_configs, auto_ai=True, user_profile=None, user_id=None):
    """Run all portal scrapers while concurrently evaluating pending jobs via Gemini in background."""
    # F15: fail before any scraping starts instead of evaluating globally.
    _require_user_id_in_multi_user(user_id, "_run_all_portals_pipelined")
    import threading
    from src.db.database import get_db_connection, is_postgres
    from src.config import AUTO_MATCH_MAX_AGE_DAYS
    from datetime import datetime, timedelta
    from src.core.utils import GERMAN_TZ

    print(f"\n{'='*60}")
    print(f"  ⚡ Concurrent Pipelined Execution: Scrapers + AI Matcher")
    print(f"{'='*60}\n")

    portal_breakdown = {}
    db_path = "data/karriere.db"
    stop_event = threading.Event()
    newly_approved_jobs = []

    # F17: record failures instead of silently returning 0 — a DB outage
    # used to look like "nothing pending". Surfaced after the join below.
    count_errors = []

    def _count_pending_jobs():
        if not (is_postgres() or os.path.exists(db_path)):
            return 0
        try:
            cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=AUTO_MATCH_MAX_AGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
            if user_id is not None:
                q = """
                    SELECT COUNT(*) FROM jobs j
                    LEFT JOIN user_jobs uj ON j.id = uj.job_id AND uj.user_id = ?
                    WHERE uj.id IS NULL AND length(j.description) > 30
                    AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
                """
                params = (user_id, cutoff)
            else:
                q = """
                    SELECT COUNT(*) FROM jobs j
                    LEFT JOIN evaluations e ON j.id = e.job_id
                    WHERE e.id IS NULL AND length(j.description) > 30
                    AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
                """
                params = (cutoff,)
            with closing(get_db_connection(db_path)) as conn:
                row = conn.cursor().execute(q, params).fetchone()
            return row[0] if row else 0
        except Exception as e:
            count_errors.append(str(e))
            if len(count_errors) == 1:
                print(f"[Warning] _count_pending_jobs failed: {e}", file=sys.stderr)
            return 0

    def _ai_consumer_worker():
        from src.ai.matcher import run_gemini_matcher_on_db
        while not stop_event.is_set():
            pending = _count_pending_jobs()
            if pending > 0:
                # Re-check quota each iteration: a long pipelined run must not
                # blow past the monthly cap after the initial gate passed.
                if user_id and not _check_ai_quota(user_id):
                    print(
                        "[Quota Warning] AI evaluations quota exhausted mid-run; "
                        "stopping AI matching for the rest of this pipeline.",
                        file=sys.stderr,
                    )
                    _alert_telegram(
                        "⚠️ *AI Quota Exhausted*\n\n"
                        "Monthly AI evaluations quota reached mid-run. "
                        "Remaining pending jobs were not evaluated."
                    )
                    break
                print(f"\n[AI Pipeline] 🚀 {pending} pending jobs detected in DB. Evaluating concurrently...")
                try:
                    approved = run_gemini_matcher_on_db(
                        db_path=db_path,
                        max_age_days=AUTO_MATCH_MAX_AGE_DAYS,
                        user_id=user_id,
                        candidate_profile=user_profile,
                    )
                    if approved:
                        newly_approved_jobs.extend(approved)
                    if user_id:
                        from src.core.entitlements import record_usage
                        record_usage(int(user_id), "ai_evaluations", 1)
                except Exception as e:
                    print(f"[AI Pipeline Error] {e}", file=sys.stderr)
            stop_event.wait(timeout=3.0)

        # Final drain sweep after all scrapers complete
        pending = _count_pending_jobs()
        if pending > 0:
            if user_id and not _check_ai_quota(user_id):
                print(
                    "[Quota Warning] AI evaluations quota exhausted before final sweep; "
                    "skipping remaining evaluations.",
                    file=sys.stderr,
                )
                _alert_telegram(
                    "⚠️ *AI Quota Exhausted*\n\n"
                    "Monthly AI evaluations quota reached before the final sweep. "
                    "Remaining pending jobs were not evaluated."
                )
            else:
                print(f"\n[AI Pipeline] 🏁 Final sweep: evaluating remaining {pending} pending jobs...")
                try:
                    approved = run_gemini_matcher_on_db(
                        db_path=db_path,
                        max_age_days=AUTO_MATCH_MAX_AGE_DAYS,
                        user_id=user_id,
                        candidate_profile=user_profile,
                    )
                    if approved:
                        newly_approved_jobs.extend(approved)
                    if user_id:
                        from src.core.entitlements import record_usage
                        record_usage(int(user_id), "ai_evaluations", 1)
                except Exception as e:
                    print(f"[AI Pipeline Error] {e}", file=sys.stderr)

    ai_quota_ok = True
    if auto_ai:
        ai_quota_ok = _check_ai_quota(user_id)
        if not ai_quota_ok:
            print(
                f"[Quota Warning] AI evaluations quota exhausted for user {user_id}. "
                "Skipping pipelined AI matching.",
                file=sys.stderr,
            )
            _alert_telegram(
                f"⚠️ *AI Quota Exhausted*\n\n"
                f"Monthly AI evaluations quota reached for user {user_id}. "
                "Skipping AI matching in pipelined run."
            )

    ai_thread = None
    if auto_ai and ai_quota_ok:
        ai_thread = threading.Thread(target=_ai_consumer_worker, daemon=True, name="AIConsumerThread")
        ai_thread.start()

    try:
        from src.scrapers.routing import get_portal_geo_params
        for p_name, p_func in p_configs:
            prev_max_id = 0
            if is_postgres() or os.path.exists(db_path):
                try:
                    # F5: closing() guarantees the connection returns to the
                    # pool / closes even when execute() raises.
                    with closing(get_db_connection(db_path)) as conn:
                        row = conn.cursor().execute("SELECT COALESCE(MAX(id), 0) FROM jobs").fetchone()
                    prev_max_id = row[0] if row else 0
                except Exception as e:
                    print(f"[Warning] Failed to fetch prev_max_id: {e}", file=sys.stderr)

            print(f"\n{'='*60}")
            print(f"  🌐 [Scraping Portal] {p_name}")
            print(f"{'='*60}\n")

            scraped_count = 0
            err = None
            try:
                p_key = p_name.lower().replace(" (ba)", "").replace(".de", "").strip()
                p_geo = get_portal_geo_params(
                    p_key,
                    user_profile.get("target_preferences", {}) if user_profile else {},
                    profile=user_profile,
                )
                p_kwargs = {}
                if user_profile:
                    p_kwargs["queries"] = build_portal_queries(user_profile, p_key)
                    p_kwargs["user_profile"] = user_profile
                if p_geo.get("location"):
                    p_kwargs["location"] = p_geo["location"]
                if p_geo.get("country_indeed"):
                    p_kwargs["country_indeed"] = p_geo["country_indeed"]

                _invoke_scraper(p_func, p_kwargs)
            except Exception as e:
                print(f"[ERROR] Failed scraping {p_name}: {e}", file=sys.stderr)
                err = str(e)
                _alert_telegram(
                    f"⚠️ *Scraper Error on {p_name}*\n\nError: {e}\nCheck run logs for details."
                )

            if is_postgres() or os.path.exists(db_path):
                try:
                    with closing(get_db_connection(db_path)) as conn:
                        row = conn.cursor().execute("SELECT COUNT(*) FROM jobs WHERE id > ?", (prev_max_id,)).fetchone()
                    scraped_count = row[0] if row else 0
                except Exception as e:
                    print(f"[Warning] Failed to count new jobs: {e}", file=sys.stderr)

            print(f"✓ {p_name}: Scraped {scraped_count} fresh jobs.")
            stats_entry = {"scraped": scraped_count, "approved": 0, "error": err}
            if auto_ai and not ai_quota_ok:
                stats_entry["quota_skipped"] = True
            portal_breakdown[p_name] = stats_entry
    finally:
        if ai_thread is not None:
            print(f"\n{'='*60}")
            print("  ⏳ All scrapers completed. Waiting for AI Matcher to finish evaluating all jobs...")
            print(f"{'='*60}\n")
            stop_event.set()
            # F6: a hung LLM call must not hang the run forever (was: join() with
            # no timeout). The matcher thread is a daemon, so the process can
            # still exit and report the run after the cap.
            ai_thread.join(timeout=1800)
            if ai_thread.is_alive():
                print(
                    "[Warning] AI matcher thread did not finish within 30 minutes; "
                    "continuing without it. The summary may undercount approvals.",
                    file=sys.stderr,
                )
                _alert_telegram(
                    "⚠️ *AI Matcher timeout*\n\nThe matcher thread did not finish within "
                    "30 minutes; the run summary may undercount approvals."
                )
            # F17: surface pending-count failures recorded by the consumer loop.
            if count_errors:
                print(
                    f"[Warning] _count_pending_jobs failed {len(count_errors)} time(s) "
                    f"during this run (last: {count_errors[-1]}); the AI consumer may "
                    "have missed pending jobs.",
                    file=sys.stderr,
                )
                _alert_telegram(
                    "⚠️ *Pending-count failures*\n\n_count_pending_jobs failed "
                    f"{len(count_errors)} time(s) during this scrape run; AI matching "
                    f"may have missed jobs. Last error: {count_errors[-1]}"
                )
        else:
            stop_event.set()

    # Tally approved per portal from newly_approved_jobs
    if newly_approved_jobs:
        for app_job in newly_approved_jobs:
            url = str(app_job.get("url") or app_job.get("job_url", "")).lower()
            matched_portal = None
            if "linkedin" in url or "licdn" in url:
                matched_portal = "LinkedIn"
            elif "indeed" in url:
                matched_portal = "Indeed"
            elif "arbeitsagentur" in url:
                matched_portal = "Bundesagentur"
            elif "bund" in url or "interamt" in url:
                matched_portal = "Bund.de"
            elif "xing" in url:
                matched_portal = "XING"
            elif "personio" in url:
                matched_portal = "Personio"
            elif "arbeitnow" in url:
                matched_portal = "Arbeitnow"
            elif "ashbyhq" in url:
                matched_portal = "Ashby"
            elif "greenhouse.io" in url:
                matched_portal = "Greenhouse"

            if matched_portal and matched_portal in portal_breakdown:
                portal_breakdown[matched_portal]["approved"] += 1

    return portal_breakdown


def handle_scrape(args):
    _acquire_scrape_lock()
    if hasattr(args, "days") and args.days:
        os.environ["SCRAPE_WINDOW"] = f"{args.days}d"
        os.environ["AUTO_MATCH_MAX_AGE_DAYS"] = str(args.days)
    if hasattr(args, "run_id") and args.run_id:
        os.environ["CURRENT_RUN_ID"] = str(args.run_id)
    if hasattr(args, "user_id") and args.user_id:
        os.environ["CURRENT_USER_ID"] = str(args.user_id)

    portal = args.portal.lower()
    auto_ai = not getattr(args, "no_match", False)
    user_id = getattr(args, "user_id", None)
    if user_id:
        from src.db.database import get_user_by_id
        from src.core.entitlements import check_rate_limit, record_usage
        user = get_user_by_id(int(user_id))
        if user:
            has_quota, quota_msg, _ = check_rate_limit(user, "scraper_runs", increment=1)
            if not has_quota:
                print(f"[Quota Error] {quota_msg}", file=sys.stderr)
                _release_scrape_lock()
                sys.exit(1)
            record_usage(int(user_id), "scraper_runs", 1)

    user_profile = get_user_profile(user_id) if user_id else None

    from src.scrapers.routing import get_portal_geo_params
    prefs = user_profile.get("target_preferences", {}) if user_profile else {}
    geo = get_portal_geo_params(
        portal,
        prefs,
        profile=user_profile,
    )
    loc = geo.get("location")
    c_ind = geo.get("country_indeed")

    portal_breakdown = {}
    total_run_scraped = 0
    total_run_approved = 0

    def _get_queries(p_name: str):
        return build_portal_queries(user_profile, p_name) if user_profile else None

    if portal == "linkedin":
        stats = _run_portal_and_ai(
            "LinkedIn",
            run_scrape_linkedin,
            auto_ai=auto_ai,
            queries=_get_queries("linkedin"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["LinkedIn"] = stats
    elif portal == "indeed":
        stats = _run_portal_and_ai(
            "Indeed",
            run_scrape_indeed,
            auto_ai=auto_ai,
            queries=_get_queries("indeed"),
            location=loc,
            country_indeed=c_ind,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["Indeed"] = stats
    elif portal == "ba":
        stats = _run_portal_and_ai(
            "Bundesagentur (BA)",
            run_scrape_ba,
            auto_ai=auto_ai,
            queries=_get_queries("ba"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["Bundesagentur"] = stats
    elif portal in ("bund", "interamt", "service.bund"):
        stats = _run_portal_and_ai(
            "Bund.de",
            run_scrape_bund,
            auto_ai=auto_ai,
            queries=_get_queries("bund"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["Bund.de"] = stats
    elif portal == "xing":
        stats = _run_portal_and_ai(
            "XING",
            run_scrape_xing,
            auto_ai=auto_ai,
            queries=_get_queries("xing"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["XING"] = stats
    elif portal == "personio":
        stats = _run_portal_and_ai(
            "Personio",
            run_scrape_personio,
            auto_ai=auto_ai,
            queries=_get_queries("personio"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["Personio"] = stats
    elif portal == "arbeitnow":
        stats = _run_portal_and_ai(
            "Arbeitnow",
            run_scrape_arbeitnow,
            auto_ai=auto_ai,
            queries=_get_queries("arbeitnow"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["Arbeitnow"] = stats
    elif portal == "ashby":
        stats = _run_portal_and_ai(
            "Ashby",
            run_scrape_ashby,
            auto_ai=auto_ai,
            queries=_get_queries("ashby"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["Ashby"] = stats
    elif portal == "greenhouse":
        stats = _run_portal_and_ai(
            "Greenhouse",
            run_scrape_greenhouse,
            auto_ai=auto_ai,
            queries=_get_queries("greenhouse"),
            location=loc,
            user_profile=user_profile,
            user_id=user_id,
        )
        portal_breakdown["Greenhouse"] = stats
    elif portal == "all":
        print(f"\n{'='*60}")
        print(f"  Job Scraper — All Portals Orchestrator (with Instant AI Processing)")
        print(f"  Window : {get_window_tag()}")
        print(f"{'='*60}\n")

        p_configs = [
            ("LinkedIn", run_scrape_linkedin),
            ("Indeed", run_scrape_indeed),
            ("Bundesagentur", run_scrape_ba),
            ("Bund.de", run_scrape_bund),
            ("XING", run_scrape_xing),
            ("Personio", run_scrape_personio),
            ("Ashby", run_scrape_ashby),
            ("Greenhouse", run_scrape_greenhouse),
            ("Arbeitnow", run_scrape_arbeitnow),
        ]

        if user_profile:
            from src.scrapers.query_builder import get_candidate_eligible_portals
            eligible_set = set(get_candidate_eligible_portals(user_profile))
            portal_key_map = {
                "linkedin": "linkedin",
                "indeed": "indeed",
                "bundesagentur": "ba",
                "bund.de": "bund",
                "xing": "xing",
                "personio": "personio",
                "ashby": "ashby",
                "greenhouse": "greenhouse",
                "arbeitnow": "arbeitnow",
            }
            p_configs = [
                (p_name, p_func) for p_name, p_func in p_configs
                if portal_key_map.get(p_name.lower(), p_name.lower()) in eligible_set
            ]
            print(f"  [Geo-Routing] Eligible portals for candidate: {', '.join(eligible_set)}")

        if user_id:
            from src.db.database import get_user_by_id
            from src.core.entitlements import get_user_tier, TIER_ENTITLEMENTS
            user_rec = get_user_by_id(user_id)
            user_tier = get_user_tier(user_rec)
            allowed_portals = set(TIER_ENTITLEMENTS.get(user_tier, TIER_ENTITLEMENTS["free"]).get("allowed_portals", []))
            portal_key_map = {
                "linkedin": "linkedin",
                "indeed": "indeed",
                "bundesagentur": "ba",
                "bund.de": "bund",
                "xing": "xing",
                "personio": "personio",
                "ashby": "ashby",
                "greenhouse": "greenhouse",
                "arbeitnow": "arbeitnow",
            }
            p_configs = [
                (p_name, p_func) for p_name, p_func in p_configs
                if portal_key_map.get(p_name.lower(), p_name.lower()) in allowed_portals
            ]
            print(f"  [Tier-Enforcement] Active Tier: {user_tier.upper()} (Allowed Portals: {', '.join(allowed_portals)})")

        if auto_ai:
            portal_breakdown = _run_all_portals_pipelined(p_configs, auto_ai=True, user_profile=user_profile, user_id=user_id)
        else:
            for p_name, p_func in p_configs:
                p_key = p_name.lower().replace(" (ba)", "").replace(".de", "").strip()
                p_queries = _get_queries(p_key)
                stats = _run_portal_and_ai(p_name, p_func, auto_ai=False, queries=p_queries)
                portal_breakdown[p_name] = stats

        print(f"\n{'='*60}")
        print("  🎉 All portals scraped and evaluated successfully!")
        print(f"{'='*60}\n")
    else:
        print(f"[ERROR] Unknown portal '{portal}'. Valid options: linkedin, indeed, ba, bund, xing, personio, ashby, greenhouse, arbeitnow, all", file=sys.stderr)
        sys.exit(1)

    total_run_scraped = sum(v.get("scraped", 0) for v in portal_breakdown.values())
    total_run_approved = sum(v.get("approved", 0) for v in portal_breakdown.values())

    # ── Auto-generate application packages (CV + Cover Letter) for 85%+ jobs ──
    gen_res = None
    auto_generate = not getattr(args, "no_generate", False)
    if auto_generate:
        try:
            from src.generators.auto_generate import auto_generate_approved_applications
            days_window = getattr(args, "days", 1) or 1
            gen_res = auto_generate_approved_applications(
                min_score=85,
                max_age_days=days_window,
                notify_telegram=False,  # Consolidated into single summary Telegram alert
            )
            print(f"✓ Auto-generation complete: {gen_res['generated_count']} generated, {gen_res['remaining_count']} left.")
        except Exception as gen_err:
            print(f"[Warning] Auto-generation error: {gen_err}", file=sys.stderr)

    # Persist latest run summary for GitHub Actions and Telegram alert
    summary_data = {
        "portal": portal,
        "run_scraped": total_run_scraped,
        "run_approved": total_run_approved,
        "breakdown": portal_breakdown,
        "auto_generate": gen_res,
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/latest_run_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        print(f"✓ Run summary written to data/latest_run_summary.json: {total_run_approved} approved, {total_run_scraped} scraped")
        
        # F1: Dispatch the structured Telegram notification for every completed
        # batch, including zero-yield runs. A clean-zero run is exactly the
        # failure mode (all scrapers silently returning nothing) that must
        # never be invisible; the notifier words it as a warning.
        try:
            from src.core.notifier import notify_scrape_summary
            summary_delivered = notify_scrape_summary(
                portal=portal,
                run_approved_count=total_run_approved,
                run_new_count=total_run_scraped,
                portal_breakdown=portal_breakdown,
                suppress_empty=False,
                auto_gen_summary=gen_res,
            )
            if total_run_scraped == 0 and total_run_approved == 0:
                if summary_delivered:
                    print("⚠️ 0 fresh jobs and 0 approved jobs — Telegram summary sent as a zero-yield warning.")
                else:
                    print(
                        "[Warning] Telegram zero-yield summary was NOT delivered; "
                        "check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID and network.",
                        file=sys.stderr,
                    )
            elif not summary_delivered:
                print("[Warning] Telegram run summary was not delivered.", file=sys.stderr)
        except Exception as notify_err:
            print(f"[Warning] Telegram summary dispatch error: {notify_err}")
    except Exception as e:
        print(f"Warning: could not save latest_run_summary.json: {e}")

    # ── Update scraper_runs in DB if run_id provided ──
    run_id = getattr(args, "run_id", None)
    if run_id:
        try:
            from src.db.database import update_scraper_run
            update_scraper_run(
                run_id=run_id,
                status="completed",
                jobs_scraped=total_run_scraped,
                jobs_matched=total_run_approved,
            )
            print(f"✓ Scraper run #{run_id} marked as completed in database (scraped: {total_run_scraped}, matched: {total_run_approved})")
        except Exception as run_err:
            print(f"[Warning] Failed to update scraper run #{run_id}: {run_err}", file=sys.stderr)


def handle_match(args):
    """Run AI evaluation directly on SQLite or any CSV."""
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — AI Matcher")
    print(f"{'='*60}\n")
    if args.file and args.file != "db" and os.path.exists(args.file) and args.file.endswith(".csv"):
        from src.ai.matcher import run_gemini_matcher
        run_gemini_matcher(
            input_csv=args.file,
            output_dir=args.outdir,
            model_name=args.model,
            limit=args.limit,
            rate_limit_delay=args.delay,
        )
    else:
        from src.ai.matcher import run_gemini_matcher_on_db
        from src.config import AUTO_MATCH_MAX_AGE_DAYS
        db_path = os.path.join(args.outdir, "karriere.db") if hasattr(args, "outdir") else "data/karriere.db"
        raw_age = getattr(args, "max_age_days", AUTO_MATCH_MAX_AGE_DAYS)
        effective_age = None if (raw_age is not None and raw_age <= 0) else (raw_age or AUTO_MATCH_MAX_AGE_DAYS)
        user_id = getattr(args, "user_id", None)
        _require_user_id_in_multi_user(user_id, "match")
        if user_id:
            from src.db.database import get_user_by_id
            from src.core.entitlements import check_rate_limit, record_usage
            user = get_user_by_id(int(user_id))
            has_quota, quota_msg, _ = check_rate_limit(user, "ai_evaluations", increment=1)
            if not has_quota:
                print(f"[Quota Error] {quota_msg}", file=sys.stderr)
                sys.exit(1)
            record_usage(int(user_id), "ai_evaluations", 1)

        user_profile = get_user_profile(user_id) if user_id else None
        run_gemini_matcher_on_db(
            model_name=args.model,
            limit=args.limit,
            rate_limit_delay=args.delay,
            db_path=db_path,
            portal=getattr(args, "portal", None),
            max_age_days=effective_age,
            user_id=user_id,
            candidate_profile=user_profile,
        )

        auto_generate = not getattr(args, "no_generate", False)
        if auto_generate:
            try:
                from src.generators.auto_generate import auto_generate_approved_applications
                gen_res = auto_generate_approved_applications(
                    min_score=85,
                    max_age_days=effective_age or 1,
                    notify_telegram=True,
                )
                print(f"✓ Auto-generation complete: {gen_res['generated_count']} generated, {gen_res['remaining_count']} left.")
            except Exception as gen_err:
                print(f"[Warning] Auto-generation error: {gen_err}", file=sys.stderr)


def handle_generate_approved(args):
    """Auto-generate tailored ATS packages for approved jobs scoring >= min-score."""
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — Auto-Generate Approved Applications")
    print(f"{'='*60}\n")
    from src.generators.auto_generate import auto_generate_approved_applications
    res = auto_generate_approved_applications(
        min_score=args.min_score,
        max_age_days=args.days,
        limit=args.limit,
        notify_telegram=not args.no_notify,
    )
    print(f"\n✓ Done: {res['generated_count']} generated, {res['remaining_count']} left in queue.")


def handle_dashboard(args):
    host = os.environ.get("DASHBOARD_HOST", DEFAULT_HOST)
    if getattr(args, "reload", False):
        from src.dashboard.reloader import run_with_reload
        run_with_reload(port=args.port, host=host)
        return
    run_server(port=args.port, host=host)


def handle_pull(args):
    """Pull the latest repository data and application files from Git or Oracle server."""
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — Sync (Pull)")
    print(f"{'='*60}\n")
    try:
        import subprocess
        if getattr(args, "server", False) or getattr(args, "prod", False) or getattr(args, "dev", False):
            script = os.path.join("scripts", "sync_from_server.sh")
            env_target = "prod" if getattr(args, "prod", False) else ("dev" if getattr(args, "dev", False) else None)
            cmd = ["bash", script]
            if env_target:
                cmd.append(env_target)
            if getattr(args, "applications_only", False):
                cmd.append("applications")
                target_desc = "applications folder only"
            else:
                target_desc = "data, seeds, and applications"
            server_label = env_target.upper() if env_target else "Oracle"
            print(f"Syncing {target_desc} directly from {server_label} server via {script}...")
            subprocess.run(cmd, check=True)
            print("✓ Synchronized from Oracle server successfully.")
            return

        from src.dashboard.git_ops import _ensure_git_safe
        _ensure_git_safe()
        print("Pulling local data and applications from origin/main...")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        from src.db.database import is_postgres, merge_databases, DB_PATH
        if is_postgres() and os.path.exists(DB_PATH):
            print("Syncing data/karriere.db into PostgreSQL...")
            stats = merge_databases(DB_PATH)
            print(f"✓ PostgreSQL database updated: {stats}")
        else:
            print("Local data/karriere.db is already current (scrapers write directly to SQLite).")
    except Exception as e:
        print(f"[ERROR] Git pull failed: {e}", file=sys.stderr)
        sys.exit(1)


def handle_sync_db(args):
    """No-op kept for backwards compatibility with old CLI invocations.

    The pipeline no longer produces CSVs; jobs are written to SQLite by
    the scrapers themselves, so there is nothing to sync.
    """
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — Sync CSVs to SQLite (no-op)")
    print(f"{'='*60}\n")
    print("Nothing to sync: scrapers write directly to data/karriere.db.")


def handle_compile(args):
    """Compile .tex files locally, update metadata and CRM, and optionally push to GitHub."""
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — Local LaTeX Compiler & Git Sync")
    print(f"{'='*60}\n")
    from src.generators.compiler import compile_all_applications
    success = compile_all_applications(clean_tex=not args.keep_tex, push_git=not args.no_push)
    if not success:
        print("[ERROR] One or more LaTeX compilations failed. See log output above.", file=sys.stderr)
        sys.exit(1)


def handle_set_tier(args):
    """Update user tier (pro / free) in database."""
    from src.db.database import get_user_by_email, update_user
    email = args.email.strip().lower()
    tier = args.tier.strip().lower()
    user = get_user_by_email(email)
    if not user:
        print(f"[ERROR] User with email '{email}' not found.", file=sys.stderr)
        sys.exit(1)
    update_user(user["id"], {"tier": tier})
    print(f"✓ Successfully updated user '{email}' (ID: {user['id']}) to tier: {tier.upper()}")



def main():
    parser = argparse.ArgumentParser(description="Karriere Pipeline Command Center CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scrape parser (WITH INSTANT PER-PORTAL AI TRIGGER)
    scrape_parser = subparsers.add_parser("scrape", help="Run scrapers and automatically evaluate fresh jobs with a configured AI provider")
    scrape_parser.add_argument(
        "--portal",
        choices=["linkedin", "indeed", "ba", "bund", "xing", "personio", "ashby", "greenhouse", "arbeitnow", "all"],
        default="all",
        help="Specify a portal to scrape, or 'all' to scrape everything (default: all)"
    )
    scrape_parser.add_argument(
        "--days",
        type=_days_arg,
        default=1,
        help="Number of days to scrape back (default: 1, e.g. 3 for weekend catch-up; range 1-30)"
    )
    scrape_parser.add_argument(
        "--no-match",
        action="store_true",
        help="Skip automatic AI evaluation after scraping"
    )
    scrape_parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Skip automatic CV/Cover letter generation for 85%%+ jobs"
    )
    scrape_parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Run scraper tailored to specified user ID profile"
    )
    scrape_parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        help="Scraper run ID in database to track status and results"
    )

    # AUTO parser (Alias)
    auto_parser = subparsers.add_parser("auto", help="Alias for scrape --portal all with automatic AI matching")
    auto_parser.add_argument(
        "--portal",
        choices=["linkedin", "indeed", "ba", "bund", "xing", "personio", "ashby", "greenhouse", "arbeitnow", "all"],
        default="all",
        help="Specify a portal to scrape (default: all)"
    )
    auto_parser.add_argument(
        "--days",
        type=_days_arg,
        default=1,
        help="Number of days to scrape back (default: 1; range 1-30)"
    )
    auto_parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Skip automatic CV/Cover letter generation for 85%%+ jobs"
    )
    auto_parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Run scraper tailored to specified user ID profile"
    )
    auto_parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        help="Scraper run ID in database to track status and results"
    )

    # Match parser (standalone AI evaluation on SQLite or optional CSV)
    match_parser = subparsers.add_parser("match", help="Directly evaluate pending jobs in SQLite DB against verified profile")
    match_parser.add_argument(
        "--file",
        default="db",
        help="Input target: 'db' (default: SQLite data/karriere.db) or optional CSV path"
    )
    match_parser.add_argument(
        "--outdir",
        default="data",
        help="Output directory (default: data)"
    )
    match_parser.add_argument(
        "--model",
        default="gemini-3-flash-preview",
        help="Gemini model ID (default: gemini-3-flash-preview)"
    )
    match_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of jobs to evaluate (for quick test)"
    )
    match_parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between API calls in seconds (default: 1.0)"
    )
    match_parser.add_argument(
        "--portal",
        type=str,
        default=None,
        help="Filter pending jobs to evaluate by portal (e.g. arbeitnow, linkedin, xing, personio)"
    )
    match_parser.add_argument(
        "--max-age-days",
        type=_max_age_arg,
        default=2,
        help="Only evaluate jobs scraped within the last N days (default: 2; pass 0 for all historical jobs; range 0-365)"
    )
    match_parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Skip automatic CV/Cover letter generation for 85%%+ jobs"
    )
    match_parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Evaluate pending jobs against specified user ID profile and save to user_jobs"
    )

    # Generate-approved parser
    gen_app_parser = subparsers.add_parser("generate-approved", help="Auto-generate CV and Cover Letter for approved jobs (>= 85%%)")
    gen_app_parser.add_argument("--min-score", type=int, default=85, help="Minimum score cutoff (default: 85)")
    gen_app_parser.add_argument("--days", type=_days_arg, default=1, help="Max age in days (default: 1; range 1-30)")
    gen_app_parser.add_argument("--limit", type=int, default=25, help="Max packages to generate (default: 25)")
    gen_app_parser.add_argument("--no-notify", action="store_true", help="Suppress Telegram alert")

# Dashboard parser
    dashboard_parser = subparsers.add_parser("dashboard", help="Launch the local job matching dashboard")
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to serve the dashboard on (default: 8000)"
    )
    dashboard_parser.add_argument(
        "--reload",
        action="store_true",
        help="Auto-restart the server when source files change (development)"
    )

    # Pull parser
    pull_parser = subparsers.add_parser("pull", help="Pull data and applications from Git and sync to SQLite")
    pull_parser.add_argument("--server", action="store_true", help="Sync directly from Oracle Cloud server via rsync")
    pull_parser.add_argument("--applications-only", action="store_true", help="Sync only applications/ directory")
    pull_parser.add_argument("--prod", action="store_true", help="Explicitly sync from production server (/opt/karriere-pipeline)")
    pull_parser.add_argument("--dev", action="store_true", help="Explicitly sync from development server (/opt/karriere-pipeline-dev)")

    # Sync-DB parser
    subparsers.add_parser("sync-db", help="Sync all CSV files in data/ into SQLite database")

    # Compile parser
    compile_parser = subparsers.add_parser("compile", help="Compile applications locally and optionally push them to GitHub")
    compile_parser.add_argument("--keep-tex", action="store_true", help="Do not delete .tex source files after compiling")
    compile_parser.add_argument("--no-push", action="store_true", help="Do not push compiled PDFs to GitHub")

    # Set user tier parser
    tier_parser = subparsers.add_parser("set-tier", help="Set user subscription tier ('pro' | 'free')")
    tier_parser.add_argument("email", type=str, help="Target user email")
    tier_parser.add_argument("tier", choices=["pro", "free"], default="pro", nargs="?", help="Tier to assign (default: pro)")

    # Sync-daemon parser
    daemon_parser = subparsers.add_parser("sync-daemon", help="Run background sync daemon to mirror server documents")
    daemon_parser.add_argument("--interval", type=int, default=300, help="Interval in seconds between syncs (default: 300)")
    daemon_parser.add_argument("--target", choices=["all", "data", "applications"], default="applications", help="Sync target (default: applications)")
    daemon_parser.add_argument("--once", action="store_true", help="Run once and exit immediately")

    # Fill parser
    fill_parser = subparsers.add_parser("fill", help="Autofill an ATS job application using Playwright with AI assistance")
    fill_parser.add_argument("url", type=str, help="Target application or job posting URL")
    fill_parser.add_argument("--cv", type=str, default=None, help="Path to tailored CV PDF")
    fill_parser.add_argument("--cover", type=str, default=None, help="Path to tailored Cover Letter PDF")
    fill_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    fill_parser.add_argument("--no-ai", dest="no_ai", action="store_true", help="Disable AI assistance (heuristic-only)")


    args = parser.parse_args()

    # F8: log the active database backend at startup; multi-user mode must
    # never silently run on the SQLite fallback.
    _db_url = os.environ.get("DATABASE_URL", "").strip()
    if _db_url:
        print("[Startup] Database backend: PostgreSQL (DATABASE_URL is set).")
    else:
        print("[Startup] Database backend: SQLite fallback (no DATABASE_URL set).")
    if _is_multi_user_mode() and not _db_url:
        print(
            "[ERROR] MULTI_USER_MODE is enabled but DATABASE_URL is not set. "
            "Refusing to start in multi-user mode on SQLite.",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.command in ("auto", "scrape"):
        try:
            handle_scrape(args)
        except (Exception, SystemExit) as e:
            run_id = getattr(args, "run_id", None)
            if run_id:
                try:
                    from src.db.database import update_scraper_run
                    err_msg = str(e) if str(e) else "Process exited or terminated"
                    update_scraper_run(
                        run_id=run_id,
                        status="failed",
                        error_message=err_msg,
                    )
                except Exception as e2:
                    print(f"[Warning] Failed to mark scraper run #{run_id} as failed: {e2}", file=sys.stderr)
            raise
    elif args.command == "match":
        handle_match(args)
    elif args.command == "generate-approved":
        handle_generate_approved(args)
    elif args.command == "dashboard":
        handle_dashboard(args)
    elif args.command == "pull":
        handle_pull(args)
    elif args.command == "sync-db":
        handle_sync_db(args)
    elif args.command == "compile":
        handle_compile(args)
    elif args.command == "set-tier":
        handle_set_tier(args)
    elif args.command == "sync-daemon":
        from scripts.auto_sync_daemon import start_sync_daemon
        start_sync_daemon(interval_seconds=args.interval, target=args.target, once=args.once)
    elif args.command == "fill":
        import asyncio
        from src.automation.form_filler import ATSFormFiller

        filler = ATSFormFiller()
        use_ai = not getattr(args, "no_ai", False)
        asyncio.run(
            filler.fill_application(
                job_url=args.url,
                cv_path=args.cv,
                cover_path=args.cover,
                headed=not args.headless,
                auto_submit=False,
                wait_for_user=True,
                use_ai=use_ai,
            )
        )


if __name__ == "__main__":
    main()
