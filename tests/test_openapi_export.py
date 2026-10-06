"""Tests for the OpenAPI export script used by the typed frontend client."""

import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_export_openapi_exposes_dashboard_paths():
    result = subprocess.run(
        [sys.executable, os.path.join("scripts", "export_openapi.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    spec = json.loads(result.stdout)

    assert "/api/jobs" in spec["paths"]
    assert "/api/datasets" in spec["paths"]
    assert "/api/applications" in spec["paths"]
    # The schema must be serializable and carry the app metadata.
    assert spec["info"]["title"] == "Karriere Pipeline Dashboard"
