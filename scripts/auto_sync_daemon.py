"""Background sync daemon to automatically synchronize server documents to local disk."""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.dashboard.git_ops import git_root


def run_sync_cycle(target: str = "applications") -> bool:
    """Execute a single sync cycle from remote server."""
    root = git_root()
    script = os.path.join(root, "scripts", "sync_from_server.sh")
    if not os.path.exists(script):
        print(f"[ERROR] Sync script not found at {script}", file=sys.stderr)
        return False

    cmd = ["bash", script, target]
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        res = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            print(f"[{now}] ✓ Background auto-sync ({target}) completed successfully.")
            return True
        else:
            print(f"[{now}] ⚠️ Auto-sync ({target}) failed (code {res.returncode}): {res.stderr.strip()}", file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Auto-sync timed out after 120s", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Auto-sync exception: {e}", file=sys.stderr)
        return False


def start_sync_daemon(interval_seconds: int = 300, target: str = "applications", once: bool = False):
    """Run sync daemon continuously or as one-shot."""
    print("=" * 60)
    print("  🔄 Karriere Pipeline — Background Auto-Sync Daemon")
    print(f"  Target: {target} | Interval: {interval_seconds}s | One-shot: {once}")
    print("=" * 60)

    if once:
        success = run_sync_cycle(target=target)
        sys.exit(0 if success else 1)

    try:
        while True:
            run_sync_cycle(target=target)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n[Info] Auto-sync daemon stopped by user.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Background sync daemon for Karriere Pipeline")
    parser.add_argument("--interval", type=int, default=300, help="Interval in seconds between syncs (default: 300)")
    parser.add_argument("--target", choices=["all", "data", "applications"], default="applications", help="Sync target")
    parser.add_argument("--once", action="store_true", help="Run once and exit immediately")
    args = parser.parse_args()

    start_sync_daemon(interval_seconds=args.interval, target=args.target, once=args.once)
