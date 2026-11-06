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
import sys
import os
import json

# Define the absolute import source
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Auto-switch to project virtualenv if running outside .venv
_venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "bin", "python"))
if os.path.exists(_venv_python) and os.path.abspath(sys.executable) != _venv_python:
    os.execv(_venv_python, [_venv_python] + sys.argv)

from src.scraper import (
    run_scrape_linkedin, run_scrape_indeed, run_scrape_ba,
    run_scrape_bund, run_scrape_xing, run_scrape_personio,
    run_scrape_arbeitnow, run_scrape_ashby
)
from src.dashboard.server import DEFAULT_HOST, run as run_server
from src.config import get_window_tag
from src.ai.matcher import run_gemini_matcher

def _run_portal_and_ai(portal_name: str, scrape_func, auto_ai: bool = True) -> dict:
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
            conn = get_db_connection(db_path)
            row = conn.cursor().execute("SELECT COALESCE(MAX(id), 0) FROM jobs").fetchone()
            prev_max_id = row[0] if row else 0
            conn.close()
        except Exception as e:
            print(f"[Warning] Failed to fetch prev_max_id: {e}", file=sys.stderr)

    try:
        scrape_func()
    except Exception as e:
        print(f"[ERROR] Failed scraping {portal_name}: {e}", file=sys.stderr)
        try:
            from src.core.notifier import send_telegram_alert
            send_telegram_alert(f"⚠️ *Scraper Error on {portal_name}*\n\nError: {e}\nCheck GitHub Actions run logs for details.")
        except Exception:
            pass
        return {"scraped": 0, "approved": 0, "error": str(e)}

    # Measure newly added jobs in Database
    if is_postgres() or os.path.exists(db_path):
        try:
            conn = get_db_connection(db_path)
            row = conn.cursor().execute("SELECT COUNT(*) FROM jobs WHERE id > ?", (prev_max_id,)).fetchone()
            scraped_count = row[0] if row else 0
            conn.close()
        except Exception as e:
            print(f"[Warning] Failed to count new jobs: {e}", file=sys.stderr)

    if auto_ai:
        # Check for ANY pending unevaluated jobs for this portal in Database
        pending_count = 0
        p_filter = ""
        p = portal_name.lower().strip()
        if "arbeitnow" in p:
            p_filter = "AND j.url LIKE '%arbeitnow%'"
        elif "linkedin" in p:
            p_filter = "AND (j.url LIKE '%linkedin%' OR j.url LIKE '%licdn%')"
        elif "xing" in p:
            p_filter = "AND j.url LIKE '%xing%'"
        elif "personio" in p:
            p_filter = "AND j.url LIKE '%personio%'"
        elif "ashby" in p:
            p_filter = "AND j.url LIKE '%ashbyhq%'"
        elif "bund" in p:
            p_filter = "AND (j.url LIKE '%bund.de%' OR j.url LIKE '%interamt.de%')"
        elif "ba" in p or "agentur" in p:
            p_filter = "AND j.url LIKE '%arbeitsagentur.de%'"
        elif "indeed" in p:
            p_filter = "AND j.url LIKE '%indeed%'"

        if is_postgres() or os.path.exists(db_path):
            try:
                from src.config import AUTO_MATCH_MAX_AGE_DAYS
                from src.core.utils import GERMAN_TZ
                from datetime import datetime, timedelta
                conn = get_db_connection(db_path)
                cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=AUTO_MATCH_MAX_AGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
                q_pending = f"""
                    SELECT COUNT(*) FROM jobs j
                    LEFT JOIN evaluations e ON j.id = e.job_id
                    WHERE e.id IS NULL AND length(j.description) > 30 {p_filter}
                    AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
                """
                cursor = conn.cursor()
                cursor.execute(q_pending, (cutoff,))
                row = cursor.fetchone()
                pending_count = row[0] if row else 0
                conn.close()
            except Exception as e:
                print(f"[Warning] Failed to count pending jobs: {e}", file=sys.stderr)
                pending_count = scraped_count

        db_label = "PostgreSQL" if is_postgres() else "SQLite"
        if pending_count > 0:
            print(f"\n{'='*60}")
            print(f"  [2/2] 🤖 Evaluating {pending_count} Pending Jobs for {portal_name} via {db_label}")
            print(f"{'='*60}\n")
            try:
                from src.ai.matcher import run_gemini_matcher_on_db
                from src.config import AUTO_MATCH_MAX_AGE_DAYS
                # Evaluate all pending jobs within recent window so no recent jobs are stranded
                approved_jobs = run_gemini_matcher_on_db(
                    db_path=db_path,
                    portal=portal_name,
                    min_job_id=None,
                    max_age_days=AUTO_MATCH_MAX_AGE_DAYS,
                )
                approved_count = len(approved_jobs) if approved_jobs else 0
            except Exception as e:
                print(f"[ERROR] Matcher failed for {portal_name}: {e}", file=sys.stderr)
                try:
                    from src.core.notifier import send_telegram_alert
                    send_telegram_alert(f"⚠️ *AI Matcher Error on {portal_name}*\n\nError: {e}")
                except Exception:
                    pass
        else:
            print(f"\n[Info] All jobs for {portal_name} already evaluated; nothing pending.")

    return {"scraped": scraped_count, "approved": approved_count}


def _run_all_portals_pipelined(p_configs, auto_ai=True):
    """Run all portal scrapers while concurrently evaluating pending jobs via Gemini in background."""
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

    def _count_pending_jobs():
        if not (is_postgres() or os.path.exists(db_path)):
            return 0
        try:
            conn = get_db_connection(db_path)
            cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=AUTO_MATCH_MAX_AGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM jobs j
                LEFT JOIN evaluations e ON j.id = e.job_id
                WHERE e.id IS NULL AND length(j.description) > 30
                AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?
                """,
                (cutoff,),
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0

    def _ai_consumer_worker():
        from src.ai.matcher import run_gemini_matcher_on_db
        while not stop_event.is_set():
            pending = _count_pending_jobs()
            if pending > 0:
                print(f"\n[AI Pipeline] 🚀 {pending} pending jobs detected in DB. Evaluating concurrently...")
                try:
                    approved = run_gemini_matcher_on_db(
                        db_path=db_path,
                        max_age_days=AUTO_MATCH_MAX_AGE_DAYS,
                    )
                    if approved:
                        newly_approved_jobs.extend(approved)
                except Exception as e:
                    print(f"[AI Pipeline Error] {e}", file=sys.stderr)
            stop_event.wait(timeout=3.0)

        # Final drain sweep after all scrapers complete
        pending = _count_pending_jobs()
        if pending > 0:
            print(f"\n[AI Pipeline] 🏁 Final sweep: evaluating remaining {pending} pending jobs...")
            try:
                approved = run_gemini_matcher_on_db(
                    db_path=db_path,
                    max_age_days=AUTO_MATCH_MAX_AGE_DAYS,
                )
                if approved:
                    newly_approved_jobs.extend(approved)
            except Exception as e:
                print(f"[AI Pipeline Error] {e}", file=sys.stderr)

    ai_thread = threading.Thread(target=_ai_consumer_worker, daemon=True, name="AIConsumerThread")
    ai_thread.start()

    try:
        for p_name, p_func in p_configs:
            prev_max_id = 0
            if is_postgres() or os.path.exists(db_path):
                try:
                    conn = get_db_connection(db_path)
                    row = conn.cursor().execute("SELECT COALESCE(MAX(id), 0) FROM jobs").fetchone()
                    prev_max_id = row[0] if row else 0
                    conn.close()
                except Exception as e:
                    print(f"[Warning] Failed to fetch prev_max_id: {e}", file=sys.stderr)

            print(f"\n{'='*60}")
            print(f"  🌐 [Scraping Portal] {p_name}")
            print(f"{'='*60}\n")

            scraped_count = 0
            err = None
            try:
                p_func()
            except Exception as e:
                print(f"[ERROR] Failed scraping {p_name}: {e}", file=sys.stderr)
                err = str(e)
                try:
                    from src.core.notifier import send_telegram_alert
                    send_telegram_alert(f"⚠️ *Scraper Error on {p_name}*\n\nError: {e}\nCheck run logs for details.")
                except Exception:
                    pass

            if is_postgres() or os.path.exists(db_path):
                try:
                    conn = get_db_connection(db_path)
                    row = conn.cursor().execute("SELECT COUNT(*) FROM jobs WHERE id > ?", (prev_max_id,)).fetchone()
                    scraped_count = row[0] if row else 0
                    conn.close()
                except Exception as e:
                    print(f"[Warning] Failed to count new jobs: {e}", file=sys.stderr)

            print(f"✓ {p_name}: Scraped {scraped_count} fresh jobs.")
            portal_breakdown[p_name] = {"scraped": scraped_count, "approved": 0, "error": err}
    finally:
        print(f"\n{'='*60}")
        print("  ⏳ All scrapers completed. Waiting for AI Matcher to finish evaluating all jobs...")
        print(f"{'='*60}\n")
        stop_event.set()
        ai_thread.join()

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

            if matched_portal and matched_portal in portal_breakdown:
                portal_breakdown[matched_portal]["approved"] += 1

    return portal_breakdown


def handle_scrape(args):
    if hasattr(args, "days") and args.days:
        os.environ["SCRAPE_WINDOW"] = f"{args.days}d"

    portal = args.portal.lower()
    auto_ai = not getattr(args, "no_match", False)

    portal_breakdown = {}
    total_run_scraped = 0
    total_run_approved = 0

    if portal == "linkedin":
        stats = _run_portal_and_ai("LinkedIn", run_scrape_linkedin, auto_ai=auto_ai)
        portal_breakdown["LinkedIn"] = stats
    elif portal == "indeed":
        stats = _run_portal_and_ai("Indeed", run_scrape_indeed, auto_ai=auto_ai)
        portal_breakdown["Indeed"] = stats
    elif portal == "ba":
        stats = _run_portal_and_ai("Bundesagentur (BA)", run_scrape_ba, auto_ai=auto_ai)
        portal_breakdown["Bundesagentur"] = stats
    elif portal in ("bund", "interamt", "service.bund"):
        stats = _run_portal_and_ai("Bund.de", run_scrape_bund, auto_ai=auto_ai)
        portal_breakdown["Bund.de"] = stats
    elif portal == "xing":
        stats = _run_portal_and_ai("XING", run_scrape_xing, auto_ai=auto_ai)
        portal_breakdown["XING"] = stats
    elif portal == "personio":
        stats = _run_portal_and_ai("Personio", run_scrape_personio, auto_ai=auto_ai)
        portal_breakdown["Personio"] = stats
    elif portal == "arbeitnow":
        stats = _run_portal_and_ai("Arbeitnow", run_scrape_arbeitnow, auto_ai=auto_ai)
        portal_breakdown["Arbeitnow"] = stats
    elif portal == "ashby":
        stats = _run_portal_and_ai("Ashby", run_scrape_ashby, auto_ai=auto_ai)
        portal_breakdown["Ashby"] = stats
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
            ("Arbeitnow", run_scrape_arbeitnow),
        ]

        if auto_ai:
            portal_breakdown = _run_all_portals_pipelined(p_configs, auto_ai=True)
        else:
            for p_name, p_func in p_configs:
                stats = _run_portal_and_ai(p_name, p_func, auto_ai=False)
                portal_breakdown[p_name] = stats

        print(f"\n{'='*60}")
        print("  🎉 All portals scraped and evaluated successfully!")
        print(f"{'='*60}\n")
    else:
        print(f"[ERROR] Unknown portal '{portal}'. Valid options: linkedin, indeed, ba, bund, xing, personio, ashby, arbeitnow, all", file=sys.stderr)
        sys.exit(1)

    total_run_scraped = sum(v.get("scraped", 0) for v in portal_breakdown.values())
    total_run_approved = sum(v.get("approved", 0) for v in portal_breakdown.values())

    # Persist latest run summary for GitHub Actions and Telegram alert
    summary_data = {
        "portal": portal,
        "run_scraped": total_run_scraped,
        "run_approved": total_run_approved,
        "breakdown": portal_breakdown
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/latest_run_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        print(f"✓ Run summary written to data/latest_run_summary.json: {total_run_approved} approved, {total_run_scraped} scraped")
        
        # Dispatch structured Telegram notification for completed batch (only if fresh activity)
        try:
            if total_run_scraped > 0 or total_run_approved > 0:
                from src.core.notifier import notify_scrape_summary
                notify_scrape_summary(
                    new_jobs_count=total_run_scraped,
                    approved_count=total_run_approved,
                    portal=portal,
                    run_approved_count=total_run_approved,
                    run_new_count=total_run_scraped,
                    portal_breakdown=portal_breakdown,
                )
            else:
                print("✓ 0 fresh jobs and 0 approved jobs; suppressing Telegram alert to avoid noise.")
        except Exception as notify_err:
            print(f"[Warning] Telegram summary dispatch error: {notify_err}")
    except Exception as e:
        print(f"Warning: could not save latest_run_summary.json: {e}")

    # ── Auto-generate application packages (CV + Cover Letter) for 85%+ jobs ──
    auto_generate = not getattr(args, "no_generate", False)
    if auto_generate:
        try:
            from src.generators.auto_generate import auto_generate_approved_applications
            days_window = getattr(args, "days", 1) or 1
            gen_res = auto_generate_approved_applications(
                min_score=85,
                max_age_days=days_window,
                notify_telegram=True,
            )
            print(f"✓ Auto-generation complete: {gen_res['generated_count']} generated, {gen_res['remaining_count']} left.")
        except Exception as gen_err:
            print(f"[Warning] Auto-generation error: {gen_err}", file=sys.stderr)


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
        run_gemini_matcher_on_db(
            model_name=args.model,
            limit=args.limit,
            rate_limit_delay=args.delay,
            db_path=db_path,
            portal=getattr(args, "portal", None),
            max_age_days=effective_age,
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
    """Pull the latest repository data and application files from Git.

    Scrapers write directly to SQLite, so there is no CSV ingestion step —
    the local DB is already current after a pull.
    """
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — Git Sync (Pull)")
    print(f"{'='*60}\n")
    try:
        import subprocess
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


def main():
    parser = argparse.ArgumentParser(description="Karriere Pipeline Command Center CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scrape parser (WITH INSTANT PER-PORTAL AI TRIGGER)
    scrape_parser = subparsers.add_parser("scrape", help="Run scrapers and automatically evaluate fresh jobs with a configured AI provider")
    scrape_parser.add_argument(
        "--portal",
        choices=["linkedin", "indeed", "ba", "bund", "xing", "personio", "ashby", "arbeitnow", "all"],
        default="all",
        help="Specify a portal to scrape, or 'all' to scrape everything (default: all)"
    )
    scrape_parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to scrape back (default: 1, e.g. 3 for weekend catch-up)"
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

    # AUTO parser (Alias)
    auto_parser = subparsers.add_parser("auto", help="Alias for scrape --portal all with automatic AI matching")
    auto_parser.add_argument(
        "--portal",
        choices=["linkedin", "indeed", "ba", "bund", "xing", "personio", "ashby", "arbeitnow", "all"],
        default="all",
        help="Specify a portal to scrape (default: all)"
    )
    auto_parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to scrape back (default: 1)"
    )
    auto_parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Skip automatic CV/Cover letter generation for 85%%+ jobs"
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
        type=int,
        default=2,
        help="Only evaluate jobs scraped within the last N days (default: 2; pass 0 for all historical jobs)"
    )
    match_parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Skip automatic CV/Cover letter generation for 85%%+ jobs"
    )

    # Generate-approved parser
    gen_app_parser = subparsers.add_parser("generate-approved", help="Auto-generate CV and Cover Letter for approved jobs (>= 85%%)")
    gen_app_parser.add_argument("--min-score", type=int, default=85, help="Minimum score cutoff (default: 85)")
    gen_app_parser.add_argument("--days", type=int, default=1, help="Max age in days (default: 1)")
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
    subparsers.add_parser("pull", help="Pull data and applications from Git and sync to SQLite")

    # Sync-DB parser
    subparsers.add_parser("sync-db", help="Sync all CSV files in data/ into SQLite database")

    # Compile parser
    compile_parser = subparsers.add_parser("compile", help="Compile applications locally and optionally push them to GitHub")
    compile_parser.add_argument("--keep-tex", action="store_true", help="Do not delete .tex source files after compiling")
    compile_parser.add_argument("--no-push", action="store_true", help="Do not push compiled PDFs to GitHub")

    args = parser.parse_args()

    if args.command in ("auto", "scrape"):
        handle_scrape(args)
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


if __name__ == "__main__":
    main()
