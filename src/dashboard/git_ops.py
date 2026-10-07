"""Git synchronization layer for the dashboard.

Isolates all repository/Git side effects (fetch/pull/rebase/push and the
background safety guards) so the HTTP adapter never shells out to git directly.
"""

import os
import subprocess
import threading

from src.core.logger import get_logger

logger = get_logger(__name__)

#: Serializes git operations between the request thread and the auto-pull worker.
GIT_LOCK = threading.Lock()


def git_root() -> str:
    """Absolute path to the repository root (two levels above this package)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _git_dir(root_dir: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root_dir,
                             capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""
    if out and not os.path.isabs(out):
        out = os.path.join(root_dir, out)
    return out


def git_in_progress(root_dir: str) -> bool:
    """True if a rebase/merge/cherry-pick is mid-flight (must not be disturbed)."""
    gd = _git_dir(root_dir)
    if not gd:
        return False
    return any(os.path.exists(os.path.join(gd, marker)) for marker in
               ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"))


def git_current_branch(root_dir: str) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root_dir,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def safe_pull_rebase(root_dir: str) -> tuple[bool, str]:
    """Pull ``origin/main`` without ever leaving a broken rebase behind.

    The dashboard's auto-sync must never rebase a checked-out feature branch
    onto ``origin/main`` (their histories can be unrelated), so the operation is
    skipped unless the current branch is the repository default. A failed rebase
    is aborted so the working tree is always left clean.
    """
    if git_in_progress(root_dir):
        return False, "a git operation is already in progress; skipped"
    branch = git_current_branch(root_dir)
    if branch not in ("main", "master"):
        return False, f"current branch is '{branch}', not 'main'; skipped to avoid rewriting unrelated history"
    subprocess.run(["git", "fetch", "origin", "main"], cwd=root_dir, capture_output=True)
    res = subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"],
                         cwd=root_dir, capture_output=True, text=True)
    if res.returncode != 0:
        subprocess.run(["git", "rebase", "--abort"], cwd=root_dir, capture_output=True)
        return False, (res.stderr or res.stdout or "pull --rebase failed").strip()
    return True, "ok"


def git_sync(message: str) -> None:
    """Commit generated applications and (only on the default branch) push to origin/main."""
    if os.environ.get("KARRIERE_GIT_SYNC", "true").lower() in {"0", "false", "no"}:
        logger.info("Git synchronization disabled by KARRIERE_GIT_SYNC.")
        return
    with GIT_LOCK:
        try:
            root_dir = git_root()
            subprocess.run(["git", "add", "applications/"], cwd=root_dir, capture_output=True)
            subprocess.run(["git", "commit", "-m", message], cwd=root_dir, capture_output=True)
            ok, detail = safe_pull_rebase(root_dir)
            if not ok:
                logger.info(f"Git sync: pull/push skipped ({detail})")
                return
            res = subprocess.run(["git", "push", "origin", "main"], cwd=root_dir, capture_output=True, text=True)
            if res.returncode == 0:
                logger.info(f"Git sync successful: {message}")
            else:
                logger.warning(f"Git sync push returned code {res.returncode}: {res.stderr}")
        except Exception as e:
            logger.error(f"Git sync failed: {e}")


def git_sync_async(message: str) -> None:
    threading.Thread(target=git_sync, args=(message,), daemon=True).start()
