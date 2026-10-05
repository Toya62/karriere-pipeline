"""Zero-dependency development file watcher / auto-reloader for the dashboard.

`python main.py dashboard --reload` runs the dashboard in a child process and
restarts it whenever a source file under the watched directories changes, so
code edits take effect without a manual Ctrl+C. Intended for local development
only; production uses a supervisor / orchestrator (see AGENTS.md).
"""

import os
import signal
import subprocess
import sys
import time

WATCH_DIRS = ["src", "dashboard"]
WATCH_EXTENSIONS = {".py", ".js", ".css", ".html", ".yml", ".yaml"}
IGNORE_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
               ".pytest_cache", "applications", "data", ".worktrees"}
POLL_INTERVAL = 1.0
DEBOUNCE_SECONDS = 0.6


def _snapshot(root: str) -> dict:
    """Return {path: mtime} for watched source files under root."""
    snap: dict = {}
    for base in WATCH_DIRS:
        directory = os.path.join(root, base)
        if not os.path.isdir(directory):
            continue
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for name in filenames:
                if os.path.splitext(name)[1].lower() not in WATCH_EXTENSIONS:
                    continue
                path = os.path.join(dirpath, name)
                try:
                    snap[path] = os.path.getmtime(path)
                except OSError:
                    pass
    return snap


def _changed_files(old: dict, new: dict) -> list:
    keys = set(old) | set(new)
    return [k for k in keys if old.get(k) != new.get(k)]


def _stop_process(proc: subprocess.Popen) -> None:
    """Stop the child and its whole process group (e.g. a launched scraper).

    The child is started in its own session, so its descendants share its
    process group; signalling the group prevents an orphaned scraper from
    surviving a reload and racing a second one on the same database.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def run_with_reload(port: int, host: str, project_root: str | None = None) -> None:
    """Run the dashboard in a child process and restart it on source changes."""
    root = os.path.abspath(project_root or os.getcwd())
    child_cmd = [sys.executable, os.path.join(root, "main.py"),
                 "dashboard", "--port", str(port)]
    env = dict(os.environ)
    env["DASHBOARD_HOST"] = host
    # Prevent a nested watcher if the child somehow re-enters.
    env.pop("KARRIERE_RELOAD", None)

    def spawn() -> subprocess.Popen:
        # New session/process group so the reloader can stop the whole tree.
        return subprocess.Popen(child_cmd, cwd=root, env=env, start_new_session=True)

    proc = spawn()
    print(f"[reload] watching {WATCH_DIRS} (ext: {sorted(WATCH_EXTENSIONS)}) — Ctrl+C to stop")
    last = _snapshot(root)
    try:
        while True:
            time.sleep(POLL_INTERVAL)
            current = _snapshot(root)

            if current != last:
                changed = _changed_files(last, current)
                # Debounce: let editors finish writing all files.
                time.sleep(DEBOUNCE_SECONDS)
                current = _snapshot(root)
                changed = _changed_files(last, current)
                last = current
                shown = ", ".join(os.path.relpath(p, root) for p in changed[:4])
                print(f"[reload] change detected ({len(changed)}): {shown}"
                      + (" …" if len(changed) > 4 else ""))
                _stop_process(proc)
                proc = spawn()
                continue

            # Child died on its own (crash) → bring it back up.
            if proc.poll() is not None:
                print("[reload] server exited; restarting…")
                proc = spawn()
                last = _snapshot(root)
    except KeyboardInterrupt:
        print("\n[reload] stopping…")
    finally:
        _stop_process(proc)
