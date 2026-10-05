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
    run_scrape_bund, run_scrape_xing, run_scrape_personio
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

    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            row = conn.cursor().execute("SELECT COALESCE(MAX(id), 0) FROM jobs").fetchone()
            prev_max_id = row[0] if row else 0
            conn.close()
        except Exception:
            pass

    try:
        scrape_func()
    except Exception as e:
        print(f"[ERROR] Failed scraping {portal_name}: {e}", file=sys.stderr)
        try:
            from src.core.notifier import send_whatsapp_alert
            send_whatsapp_alert(f"⚠️ *Scraper Error on {portal_name}*\n\nError: {e}\nCheck GitHub Actions run logs for details.")
        except Exception:
            pass
        return {"scraped": 0, "approved": 0}

    # Measure newly added jobs in SQLite
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            row = conn.cursor().execute("SELECT COUNT(*) FROM jobs WHERE id > ?", (prev_max_id,)).fetchone()
            scraped_count = row[0] if row else 0
            conn.close()
        except Exception:
            pass

    if auto_ai:
        if scraped_count > 0:
            print(f"\n{'='*60}")
            print(f"  [2/2] 🤖 Instantly Evaluating {scraped_count} Fresh Jobs via SQLite")
            print(f"{'='*60}\n")
            try:
                from src.ai.matcher import run_gemini_matcher_on_db
                approved_jobs = run_gemini_matcher_on_db(
                    db_path=db_path,
                    min_job_id=prev_max_id + 1 if prev_max_id > 0 else None
                )
                approved_count = len(approved_jobs) if approved_jobs else 0
            except Exception as e:
                print(f"[ERROR] Matcher failed for {portal_name}: {e}", file=sys.stderr)
                try:
                    from src.core.notifier import send_whatsapp_alert
                    send_whatsapp_alert(f"⚠️ *AI Matcher Error on {portal_name}*\n\nError: {e}")
                except Exception:
                    pass
        else:
            print(f"\n[Info] No new jobs scraped for {portal_name}; skipping instant evaluation.")

    return {"scraped": scraped_count, "approved": approved_count}


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
        ]

        for p_name, p_func in p_configs:
            stats = _run_portal_and_ai(p_name, p_func, auto_ai=auto_ai)
            portal_breakdown[p_name] = stats

        print(f"\n{'='*60}")
        print("  🎉 All portals scraped and evaluated successfully!")
        print(f"{'='*60}\n")
    else:
        print(f"[ERROR] Unknown portal '{portal}'. Valid options: linkedin, indeed, ba, bund, xing, personio, all", file=sys.stderr)
        sys.exit(1)

    total_run_scraped = sum(v.get("scraped", 0) for v in portal_breakdown.values())
    total_run_approved = sum(v.get("approved", 0) for v in portal_breakdown.values())

    # Persist latest run summary for GitHub Actions and WhatsApp alert
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
    except Exception as e:
        print(f"Warning: could not save latest_run_summary.json: {e}")


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
            rate_limit_delay=args.delay
        )
    else:
        from src.ai.matcher import run_gemini_matcher_on_db
        db_path = os.path.join(args.outdir, "karriere.db") if hasattr(args, "outdir") else "data/karriere.db"
        run_gemini_matcher_on_db(
            model_name=args.model,
            limit=args.limit,
            rate_limit_delay=args.delay,
            db_path=db_path
        )


def handle_dashboard(args):
    run_server(port=args.port, host=os.environ.get("DASHBOARD_HOST", DEFAULT_HOST))


def handle_pull(args):
    """Pull the latest repository data and application files from Git and sync to SQLite."""
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — Git Sync (Pull & SQLite Ingestion)")
    print(f"{'='*60}\n")
    try:
        import subprocess
        print("Pulling local data and applications from origin/main...")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        print("Syncing pulled data into data/karriere.db...")
        from src.db import sync_all_csvs_to_db
        sync_all_csvs_to_db()
    except Exception as e:
        print(f"[ERROR] Git pull or DB sync failed: {e}", file=sys.stderr)
        sys.exit(1)


def handle_sync_db(args):
    """Sync all CSV files in data/ into data/karriere.db."""
    print(f"\n{'='*60}")
    print(f"  Karriere Pipeline — Sync CSVs to SQLite Database")
    print(f"{'='*60}\n")
    from src.db import sync_all_csvs_to_db
    sync_all_csvs_to_db()


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
        choices=["linkedin", "indeed", "ba", "bund", "xing", "personio", "all"],
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

    # AUTO parser (Alias)
    auto_parser = subparsers.add_parser("auto", help="Alias for scrape --portal all with automatic AI matching")
    auto_parser.add_argument(
        "--portal",
        choices=["linkedin", "indeed", "ba", "bund", "xing", "personio", "all"],
        default="all",
        help="Specify a portal to scrape (default: all)"
    )
    auto_parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to scrape back (default: 1)"
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
        default="gemini-3.5-flash-lite",
        help="Gemini model ID (default: gemini-3.5-flash-lite)"
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
        default=4.1,
        help="Delay between API calls in seconds (default: 4.1 for 15 RPM free tier)"
    )

# Dashboard parser
    dashboard_parser = subparsers.add_parser("dashboard", help="Launch the local job matching dashboard")
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to serve the dashboard on (default: 8000)"
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
