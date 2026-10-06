import subprocess
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import handle_pull
from src.dashboard.app import create_app


def test_dashboard_serves_application_pdf_from_local_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "applications" / "2026-06-25" / "sample_cv.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"local-pdf-content")

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get("/applications/2026-06-25/sample_cv.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"local-pdf-content"
    client.close()


def test_pull_command_uses_git_only(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))

    handle_pull(SimpleNamespace())

    assert calls == [(["git", "pull", "--rebase", "origin", "main"], {"check": True})]
    assert "S3" not in capsys.readouterr().out


def test_runtime_has_no_aws_storage_dependency_or_jenkins_credentials():
    project_root = Path(__file__).parents[1]
    requirements = (project_root / "requirements.txt").read_text(encoding="utf-8").lower()
    jenkinsfile = (project_root / "Jenkinsfile").read_text(encoding="utf-8").lower()

    assert "boto3" not in requirements
    assert "aws_access_key_id" not in jenkinsfile
    assert "aws_secret_access_key" not in jenkinsfile
    assert "s3_bucket_name" not in jenkinsfile
    assert not (project_root / "src" / "s3_helper.py").exists()


def test_atomic_csv_write(tmp_path):
    """Verify that _save_csv writes atomically and leaves no corrupted partial files."""
    import os

    import pandas as pd

    from src.db.file_io import _save_csv

    test_csv = str(tmp_path / "test_data.csv")
    df = pd.DataFrame([{"title": "Dev", "company": "TestCorp", "job_url": "https://example.com/job1"}])

    _save_csv(df, test_csv)
    assert os.path.exists(test_csv)

    loaded = pd.read_csv(test_csv)
    assert len(loaded) == 1
    assert loaded.iloc[0]["company"] == "TestCorp"

    # Verify no dangling temp files left behind
    temp_files = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert len(temp_files) == 0