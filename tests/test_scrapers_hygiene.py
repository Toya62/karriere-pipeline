from datetime import datetime, timedelta, timezone

import pandas as pd


def test_ba_scraper_keeps_tls_verification_enabled(monkeypatch):
    from src.scrapers import ba

    request_options = []

    class EmptySearchResponse:
        ok = True

        @staticmethod
        def json():
            return {}

    def fake_get(*args, **kwargs):
        request_options.append(kwargs)
        return EmptySearchResponse()

    monkeypatch.setattr(ba.requests, "get", fake_get)

    assert ba.scrape_arbeitsagentur("Python", max_results=1) == []
    assert request_options
    assert all(options.get("verify", True) is True for options in request_options)


def test_bund_and_xing_runners_apply_requested_date_window(monkeypatch, tmp_path):
    import src.db.file_io as file_io
    import src.filters as filters
    import src.scrapers.bund as bund
    import src.scrapers.xing as xing
    import src.scrapers.orchestrator as orchestrator

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SCRAPE_WINDOW", "1d")
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    old = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
    jobs = pd.DataFrame([
        {"title": "Python Engineer", "company": "Recent Co", "date_posted": recent, "description": "recent"},
        {"title": "Python Engineer", "company": "Old Co", "date_posted": old, "description": "old"},
    ])

    for module in (bund, xing):
        monkeypatch.setattr(module, "scrape_bund" if module is bund else "scrape_xing", lambda: jobs.copy())

    for name in (
        "filter_seniority", "filter_experience", "filter_noise", "filter_cs_relevance",
        "filter_research_cs", "filter_forbidden_tech", "filter_language",
        "filter_seen_reposts", "filter_seen_reposts_by_url",
    ):
        monkeypatch.setattr(filters, name, lambda frame, *args, **kwargs: frame)
    monkeypatch.setattr(orchestrator, "_ALL_TIME_FILES", [])
    monkeypatch.setattr(file_io, "_save_csv", lambda *args, **kwargs: None)
    monkeypatch.setattr(file_io, "update_all_time", lambda *args, **kwargs: None)

    bund_jobs = bund.run_scrape_bund()
    xing_jobs = xing.run_scrape_xing()

    assert bund_jobs["company"].tolist() == ["Recent Co"]
    assert xing_jobs["company"].tolist() == ["Recent Co"]
