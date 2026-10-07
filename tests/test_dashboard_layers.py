"""Tests guarding the dashboard's layered architecture.

The data/side-effect layers (`crm`, `dismissals`, `git_ops`) must be usable
without importing the HTTP adapter (`server`), so they stay testable and
reusable by the CLI/compiler paths.
"""

import os
import sqlite3
import subprocess
import sys

from src.dashboard import crm, dismissals, git_ops  # noqa: F401  (import must succeed)


def _init_schema(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT NOT NULL, "
        "title TEXT NOT NULL, url TEXT, location TEXT, description TEXT, scraped_at TEXT, "
        "UNIQUE(company, title))"
    )
    c.execute(
        "CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, "
        "cv_pdf_path TEXT, cover_pdf_path TEXT, status TEXT DEFAULT 'Prepared', "
        "applied_at TEXT, notes TEXT, UNIQUE(job_id))"
    )
    conn.commit()
    conn.close()


def test_crm_layer_usable_without_server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    _init_schema("data/karriere.db")

    assert crm.upsert_tracker_row("ACME", "Dev", "https://example.com/job/1", notes="n") is True

    conn = sqlite3.connect("data/karriere.db")
    row = conn.execute("SELECT status FROM applications").fetchone()
    conn.close()
    # A freshly created CRM row starts as "Prepared" (DEFAULT_NEW_STATUS);
    # it is never auto-advanced to "Applied" until the user marks it applied.
    assert row == ("Prepared",)


def test_url_only_update_is_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    _init_schema("data/karriere.db")
    crm.upsert_tracker_row("ACME", "Dev", "https://example.com/job/1", status="Applied")

    # URL-only lookup (no company/title) must resolve an existing application.
    assert crm.upsert_tracker_row("", "", "https://example.com/job/1", status="Offer", create=False) is True

    conn = sqlite3.connect("data/karriere.db")
    status = conn.execute("SELECT status FROM applications WHERE job_id = 1").fetchone()[0]
    conn.close()
    assert status == "Offer"


def test_create_initializes_missing_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    assert not os.path.exists("data/karriere.db")

    assert crm.upsert_tracker_row("ACME", "Dev", "https://example.com/job/1", notes="n") is True
    assert os.path.exists("data/karriere.db")


def test_git_layer_available_without_repo(tmp_path):
    root = git_ops.git_root()
    assert os.path.isabs(root)
    ok, detail = git_ops.safe_pull_rebase(str(tmp_path))  # not a repo -> must not raise
    assert ok is False
    assert isinstance(detail, str)


def test_layers_do_not_import_http_adapter():
    for module in ("src.dashboard.crm", "src.dashboard.dismissals", "src.dashboard.git_ops"):
        probe = (
            "import importlib, sys; "
            f"importlib.import_module('{module}'); "
            "sys.exit(1 if 'src.dashboard.server' in sys.modules else 0)"
        )
        result = subprocess.run([sys.executable, "-c", probe], cwd=os.getcwd())
        assert result.returncode == 0, f"{module} pulled in src.dashboard.server"
