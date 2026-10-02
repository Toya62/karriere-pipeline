import csv
import subprocess
import socketserver
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from src.dashboard.server import DashboardHandler
from main import handle_pull


def test_dashboard_serves_application_pdf_from_local_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "applications" / "2026-06-25" / "sample_cv.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"local-pdf-content")

    server = socketserver.TCPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/applications/2026-06-25/sample_cv.pdf"
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            assert response.geturl() == url
            assert response.read() == b"local-pdf-content"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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