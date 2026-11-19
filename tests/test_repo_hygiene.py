"""Tests for repository secret hygiene, gitignore enforcement, and sensitive credential protection."""

import subprocess
from pathlib import Path


def test_private_config_files_in_gitignore():
    root = Path(__file__).parent.parent
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    
    assert ".env" in gitignore
    assert "user_profile.yml" in gitignore
    assert "*.db" in gitignore or "data/*" in gitignore


def test_tracked_git_files_contain_no_live_private_keys():
    """Verify no live private keys or tokens are tracked in git."""
    root = Path(__file__).parent.parent
    res = subprocess.run(
        ["git", "grep", "-E", "AIzaSy[0-9A-Za-z_-]{33}", "--", ":!tests/fixtures*"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0, f"Found exposed Gemini API key in git tracked files: {res.stdout}"
