"""Tests for the dashboard git-sync guard (prevents rebasing feature branches).

These guard against the failure mode where ``git pull --rebase origin main``
was run on a feature branch with unrelated history, leaving conflict markers.
"""

import subprocess

from src.dashboard import server


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_git_in_progress_detects_rebase(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".git" / "rebase-merge").mkdir()
    assert server._git_in_progress(str(tmp_path)) is True


def test_git_in_progress_false_when_clean(tmp_path):
    _init_repo(tmp_path)
    assert server._git_in_progress(str(tmp_path)) is False


def test_safe_pull_skips_non_main_branch(tmp_path):
    _init_repo(tmp_path)
    subprocess.run(["git", "checkout", "-q", "-b", "feature/x"], cwd=tmp_path, check=True)

    ok, detail = server._safe_pull_rebase(str(tmp_path))

    assert ok is False
    assert "not 'main'" in detail


def test_safe_pull_skips_when_operation_in_progress(tmp_path):
    _init_repo(tmp_path)
    # Simulate a stuck rebase on the main branch.
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=tmp_path, check=True)
    (tmp_path / ".git" / "rebase-merge").mkdir()

    ok, detail = server._safe_pull_rebase(str(tmp_path))

    assert ok is False
    assert "in progress" in detail
