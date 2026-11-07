#!/usr/bin/env python3
"""
CLI entrypoint for ATS Auto-Form Filling Assistant.
Usage:
    python scripts/auto_apply.py --demo
    python scripts/auto_apply.py applications/2026-11-07/meteocontrol_ot-security-engineer.meta.json
    python scripts/auto_apply.py --url "https://jobs.ashbyhq.com/..." --cv path/to/cv.pdf
"""

import sys
import os
import glob
import json
import asyncio
import argparse
from pathlib import Path

# Add repo root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.automation.form_filler import ATSFormFiller, run_form_fill_demo


def main():
    parser = argparse.ArgumentParser(description="ATS Auto-Form Filling Assistant")
    parser.add_argument("meta_file", nargs="?", help="Path to .meta.json application file")
    parser.add_argument("--demo", action="store_true", help="Run interactive demo with latest prepared application")
    parser.add_argument("--url", help="Direct job apply URL")
    parser.add_argument("--cv", help="Direct CV PDF path")
    parser.add_argument("--cover", help="Direct Cover Letter PDF path")
    parser.add_argument("--headless", action="store_true", help="Run without visible browser window")
    args = parser.parse_args()

    meta_target = args.meta_file

    if args.demo and not meta_target:
        # Find latest compiled application from applications/
        all_metas = sorted(glob.glob("applications/*/*.meta.json"), key=os.path.getmtime, reverse=True)
        # Prefer personio or ashby
        for m in all_metas:
            with open(m, "r", encoding="utf-8") as f:
                data = json.load(f)
                url = data.get("apply_url") or data.get("job_url") or ""
                if "personio" in url or "ashby" in url:
                    meta_target = m
                    break
        if not meta_target and all_metas:
            meta_target = all_metas[0]

    if meta_target:
        asyncio.run(run_form_fill_demo(meta_target, headed=not args.headless))
    elif args.url:
        filler = ATSFormFiller()
        asyncio.run(
            filler.fill_application(
                job_url=args.url,
                cv_path=args.cv,
                cover_path=args.cover,
                headed=not args.headless,
                auto_submit=False
            )
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
