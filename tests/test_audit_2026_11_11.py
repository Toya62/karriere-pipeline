"""Regression tests for audit 2026-11-11 findings (F1, F3, F4, F16, F18).

Run: pytest tests/test_audit_2026_11_11.py -v
"""
import argparse
import os

import pytest


# ── F16: CLI numeric validation ────────────────────────────────────────────
def test_days_arg_accepts_valid_range():
    import main

    assert main._days_arg("1") == 1
    assert main._days_arg("30") == 30


def test_days_arg_rejects_out_of_range_and_non_integer():
    import main

    for bad in ("0", "31", "-3", "abc"):
        with pytest.raises(argparse.ArgumentTypeError):
            main._days_arg(bad)


def test_max_age_arg_accepts_zero_for_all_history():
    import main

    assert main._max_age_arg("0") == 0
    assert main._max_age_arg("365") == 365


def test_max_age_arg_rejects_invalid():
    import main

    for bad in ("-1", "366", "abc"):
        with pytest.raises(argparse.ArgumentTypeError):
            main._max_age_arg(bad)


def test_auto_match_max_age_days_fails_fast_on_bad_env(monkeypatch):
    import main

    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "not-a-number")
    with pytest.raises(ValueError, match="AUTO_MATCH_MAX_AGE_DAYS"):
        main._get_auto_match_max_age_days()

    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "400")
    with pytest.raises(ValueError, match="between 0 and 365"):
        main._get_auto_match_max_age_days()


# ── F3: hostile portal slug must be rejected, never interpolated into SQL ──
def test_hostile_portal_slug_rejected(monkeypatch):
    import main

    monkeypatch.delenv("MULTI_USER_MODE", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "2")

    calls = []

    def fake_scraper(**kwargs):
        calls.append(kwargs)

    with pytest.raises(ValueError, match="Unknown portal slug"):
        main._run_portal_and_ai("x' OR '1'='1", fake_scraper, auto_ai=True)
    assert calls == [{}] or len(calls) == 1  # scraper ran; the query never did


def test_known_portals_pass_allowlist(monkeypatch, tmp_path, capsys):
    import main

    monkeypatch.delenv("MULTI_USER_MODE", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "2")
    monkeypatch.chdir(tmp_path)  # no data/karriere.db -> DB blocks are skipped

    stats = main._run_portal_and_ai("LinkedIn", lambda **kw: None, auto_ai=True)
    assert stats == {"scraped": 0, "approved": 0}


# ── F4: scraper invocation must not mask genuine TypeErrors ───────────────
def test_invoke_scraper_only_passes_accepted_kwargs():
    import main

    seen = {}

    def scraper(queries=None):
        seen.update({"queries": queries})

    main._invoke_scraper(scraper, {"queries": ["python"], "location": "Berlin", "user_profile": {"x": 1}})
    assert seen == {"queries": ["python"]}


def test_invoke_scraper_surfaces_real_typeerror_exactly_once():
    import main

    calls = []

    def broken():
        calls.append(1)
        raise TypeError("boom inside scraper")

    with pytest.raises(TypeError, match="boom inside scraper"):
        main._invoke_scraper(broken, {"queries": ["python"]})
    assert len(calls) == 1  # was retried up to 2 extra times before the fix


# ── F15: user_id is mandatory in multi-user mode ──────────────────────────
def test_require_user_id_in_multi_user_mode(monkeypatch):
    import main

    monkeypatch.setenv("MULTI_USER_MODE", "true")
    with pytest.raises(ValueError, match="user_id is required in multi-user mode"):
        main._require_user_id_in_multi_user(None, "test")

    main._require_user_id_in_multi_user(1, "test")  # admin is a normal user now

    monkeypatch.delenv("MULTI_USER_MODE")
    main._require_user_id_in_multi_user(None, "test")  # single-user mode: fine


# ── F1: zero-yield summaries are sent and worded as a warning ─────────────
def test_zero_yield_summary_worded_as_warning(monkeypatch):
    from src.core import notifier

    captured = {}

    def fake_send(msg):
        captured["msg"] = msg
        return True

    monkeypatch.setattr(notifier, "send_telegram_alert", fake_send)

    sent = notifier.notify_scrape_summary(
        run_new_count=0,
        run_approved_count=0,
        portal="all",
        suppress_empty=False,
    )
    assert sent is True
    assert "Zero-yield run" in captured["msg"]
    assert "failing silently" in captured["msg"]


def test_nonzero_summary_has_no_zero_yield_warning(monkeypatch):
    from src.core import notifier

    captured = {}

    def fake_send(msg):
        captured["msg"] = msg
        return True

    monkeypatch.setattr(notifier, "send_telegram_alert", fake_send)

    notifier.notify_scrape_summary(
        run_new_count=3,
        run_approved_count=1,
        portal="all",
        suppress_empty=False,
    )
    assert "Zero-yield" not in captured["msg"]


def test_scrape_summary_consolidates_auto_gen_and_backlog(monkeypatch):
    from src.core import notifier

    captured = {}
    monkeypatch.setattr(notifier, "send_telegram_alert", lambda msg: (captured.update({"msg": msg}), True)[1])
    monkeypatch.setattr(notifier, "get_today_pipeline_stats", lambda: (183, 71))

    notifier.notify_scrape_summary(
        run_new_count=43,
        run_approved_count=36,
        portal="all",
        portal_breakdown={
            "LinkedIn": {"scraped": 35, "approved": 35},
            "Indeed": {"scraped": 8, "approved": 0},
            "Ashby": {"scraped": 0, "approved": 1},
        },
        auto_gen_summary={
            "generated_count": 36,
            "remaining_count": 0,
            "failed_count": 0,
            "generated_jobs": [
                {"title": "C++ Engineer", "company": "Siemens", "score": 95},
                {"title": "Python Dev", "company": "BMW", "score": 90},
            ],
        },
        suppress_empty=False,
    )

    msg = captured["msg"]
    # Consolidated message checks
    assert "Auto-Generation Pipeline Complete" in msg
    assert "Generated Packages:* 36" in msg
    assert "Siemens" in msg
    # Backlog note on 0 fresh + approved
    assert "backlog evaluated" in msg
    # Cumulative today stats from DB
    assert "AI Approved (Today):* 71" in msg
    assert "Total Scraped (Today):* 183" in msg
    assert "New Approved (This Run):* +36" in msg


# ── F18: alert delivery failure is reported, not swallowed ────────────────
def test_alert_telegram_reports_failed_delivery(monkeypatch, capsys):
    import main
    from src.core import notifier

    monkeypatch.setattr(notifier, "send_telegram_alert", lambda msg: False)
    assert main._alert_telegram("test") is False
    assert "was not delivered" in capsys.readouterr().err
