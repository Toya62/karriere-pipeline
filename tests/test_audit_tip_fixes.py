import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.dashboard.app import app
from src.core.security import create_access_token

client = TestClient(app)

def test_scraper_sources_endpoint():
    token = create_access_token({"user_id": 1, "email": "admin@example.com", "role": "admin", "tier": "pro"})
    resp = client.get("/api/scraper/sources", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert len(data["sources"]) >= 7
    source_ids = [s["id"] for s in data["sources"]]
    assert "ba" in source_ids
    assert "linkedin" in source_ids
    assert "arbeitnow" in source_ids
    for s in data["sources"]:
        assert "jobs_count" in s
        assert "status" in s
        assert "eligible" in s

def test_funnel_stats_date_filtering():
    token = create_access_token({"user_id": 1, "email": "admin@example.com", "role": "admin", "tier": "pro"})
    resp = client.get("/api/funnel-stats?days=7", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "counts" in data
    assert "weekly_activity" in data
    if data["weekly_activity"]:
        for w in data["weekly_activity"]:
            assert "week" in w
            assert "'" in w["week"] or "20" in w["week"]
