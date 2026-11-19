import io
import zipfile
from fastapi.testclient import TestClient
from src.dashboard.app import app

client = TestClient(app)

def test_extension_download_returns_valid_zip():
    resp = client.get("/api/extension/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment; filename=\"sarathi-extension.zip\"" in resp.headers["content-disposition"]

    # Read zip bytes and inspect contents
    zip_bytes = io.BytesIO(resp.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "background.js" in names
        assert "content.js" in names
        assert "popup.html" in names
        # Ensure no junk files included
        assert not any(".DS_Store" in n for n in names)
        assert not any("__pycache__" in n for n in names)

def test_extension_info_endpoint():
    resp = client.get("/api/extension/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["download_url"] == "/api/extension/download"
    assert "Sarathi" in data["manifest_name"]
    assert "version" in data
