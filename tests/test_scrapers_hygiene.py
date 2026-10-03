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


def test_dynamic_scrape_window_config():
    """Verify that SCRAPE_WINDOW changes dynamically reflect in MAX_DAYS and WINDOW_TAG."""
    import os
    import src.config as config

    orig = os.environ.get("SCRAPE_WINDOW")
    try:
        os.environ["SCRAPE_WINDOW"] = "1d"
        assert config.MAX_DAYS == 1
        assert config.WINDOW_TAG == "1d"

        os.environ["SCRAPE_WINDOW"] = "7d"
        assert config.MAX_DAYS == 7
        assert config.WINDOW_TAG == "7d"

        os.environ["SCRAPE_WINDOW"] = "3"
        assert config.MAX_DAYS == 3
        assert config.WINDOW_TAG == "3d"
    finally:
        if orig is not None:
            os.environ["SCRAPE_WINDOW"] = orig
        else:
            os.environ.pop("SCRAPE_WINDOW", None)


def test_linkedin_orchestrator_uses_runtime_scrape_window(monkeypatch):
    import importlib
    import sys
    from types import ModuleType
    import src.scrapers.orchestrator as orchestrator_module

    monkeypatch.setenv("SCRAPE_WINDOW", "1d")
    importlib.reload(orchestrator_module)

    observed_hours = []
    linkedin_module = ModuleType("src.scrapers.linkedin")
    linkedin_module.scrape_linkedin = lambda query, results_wanted, hours_old: (
        observed_hours.append(hours_old) or pd.DataFrame()
    )
    linkedin_module.hydrate_linkedin_jobs = lambda jobs, max_workers: jobs
    monkeypatch.setitem(sys.modules, "src.scrapers.linkedin", linkedin_module)
    monkeypatch.setattr(orchestrator_module, "BOOLEAN_QUERIES", ["test query"])
    monkeypatch.setattr(orchestrator_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(orchestrator_module, "finalise", lambda *args, **kwargs: None)
    monkeypatch.setenv("SCRAPE_WINDOW", "7d")

    orchestrator_module.run_scrape_linkedin()

    assert observed_hours == [174]


def test_scraper_wrappers_use_runtime_scrape_window(monkeypatch):
    import importlib
    from src.scrapers import indeed, linkedin

    monkeypatch.setenv("SCRAPE_WINDOW", "1d")
    importlib.reload(linkedin)
    importlib.reload(indeed)
    observed_hours = {}
    monkeypatch.setattr(
        linkedin,
        "scrape_jobs",
        lambda **kwargs: observed_hours.update(linkedin=kwargs["hours_old"]) or pd.DataFrame(),
    )
    monkeypatch.setattr(
        indeed,
        "scrape_jobs",
        lambda **kwargs: observed_hours.update(indeed=kwargs["hours_old"]) or pd.DataFrame(),
    )
    monkeypatch.setenv("SCRAPE_WINDOW", "7d")

    linkedin.scrape_linkedin("test query")
    indeed.scrape_indeed("test query")

    assert observed_hours == {"linkedin": 174, "indeed": 168}


def test_all_portals_banner_uses_runtime_scrape_window(monkeypatch, tmp_path, capsys):
    import importlib
    from types import SimpleNamespace
    import main as main_module

    monkeypatch.setenv("SCRAPE_WINDOW", "1d")
    importlib.reload(main_module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main_module,
        "_run_portal_and_ai",
        lambda *args, **kwargs: {"scraped": 0, "approved": 0},
    )
    monkeypatch.setattr("src.db.file_io.rebuild_all_time_combined", lambda: None)

    main_module.handle_scrape(SimpleNamespace(days=7, portal="all", no_match=True))

    assert "Window : 7d" in capsys.readouterr().out

