import io
import sqlite3
import urllib.error

import pytest

from src.ai.prefilter import prefilter_job


@pytest.mark.parametrize("title,status", [
    ("Werkstudent Softwareentwicklung (m/w/d)", "REJECTED_EMPLOYMENT_TYPE"),
    ("Working Student Data Engineering", "REJECTED_EMPLOYMENT_TYPE"),
    ("Praktikum Backend", "REJECTED_EMPLOYMENT_TYPE"),
    ("Praktikant IT", "REJECTED_EMPLOYMENT_TYPE"),
    ("Software Engineering Internship", "REJECTED_EMPLOYMENT_TYPE"),
    ("Minijob Webentwicklung", "REJECTED_EMPLOYMENT_TYPE"),
    ("Geringfügige Beschäftigung IT-Support", "REJECTED_EMPLOYMENT_TYPE"),
    ("Senior Python Developer", "REJECTED_SENIORITY_EXP"),
    ("Tech Lead Backend", "REJECTED_SENIORITY_EXP"),
    ("Principal Engineer", "REJECTED_SENIORITY_EXP"),
    ("Head of Engineering", "REJECTED_SENIORITY_EXP"),
    ("Solution Architect", "REJECTED_SENIORITY_EXP"),
    ("Leiter Softwareentwicklung", "REJECTED_SENIORITY_EXP"),
    ("Senior-Entwickler (m/w/d)", "REJECTED_SENIORITY_EXP"),
    ("Postdoc - Data Engineering", "REJECTED_EMPLOYMENT_TYPE"),
    ("VIE - Fleet Data Analyst", "REJECTED_EMPLOYMENT_TYPE"),
    ("Data Analyst / Controller - BI & Finance", "REJECTED_OUT_OF_PROFILE_DOMAIN"),
    ("Marketing Digitalisierung Manager", "REJECTED_OUT_OF_PROFILE_DOMAIN"),
    ("Backend Engineer (Golang)", "REJECTED_OUT_OF_PROFILE_DOMAIN"),
])
def test_positive_title_matches(title, status):
    res = prefilter_job(title, "x" * 100)
    assert res is not None and res["status"] == status
    assert res["is_approved"] is False
    assert set(res) == {"status", "is_approved", "interview_chance", "match_score",
                        "recommended_doc_language", "decision_summary"}


@pytest.mark.parametrize("title", [
    "Seniorenbetreuung IT-Support",
    "Leadership Trainer Python",
    "Leadgenerierung Backend",
    "Internal Tools Developer",
    "Internationale Softwareentwicklung",
    "Software Engineer (m/w/d)",
    "Architecture Documentation Writer",
    "",
])
def test_false_positives_not_rejected(title):
    assert prefilter_job(title, "x" * 100) is None


def test_description_only_mentions_are_ignored():
    assert prefilter_job("Python Developer", "Senior team, Praktikum possible") is None


def test_fulltime_option_prevents_employment_type_rejection():
    assert prefilter_job("Werkstudent oder Vollzeit Entwickler", "") is None
    assert prefilter_job("Praktikum Backend", "Auch in Full-Time möglich") is None


def test_evaluate_single_job_prefilter_toggle(monkeypatch):
    from src.ai import matcher

    def boom(**kwargs):
        raise AssertionError("AI must not be called")

    monkeypatch.setattr(matcher, "route_ai_evaluation", boom)
    row = {"title": "Senior Python Developer", "company": "Acme", "description": "d" * 100}
    assert matcher.evaluate_single_job(row)["status"] == "REJECTED_SENIORITY_EXP"

    monkeypatch.setattr(matcher.config, "AI_PREFILTER_ENABLED", False)
    monkeypatch.setattr(matcher, "route_ai_evaluation", lambda **kw: {"status": "APPROVED"})
    assert matcher.evaluate_single_job(row)["status"] == "APPROVED"


def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b""))


def test_router_disables_dead_provider_once(monkeypatch, caplog):
    from src.ai.router import AIRouter

    r = AIRouter()
    r.keys = {"groq": ["k"], "openrouter": ["k"]}
    calls = {"groq": 0, "or": 0}

    def groq(*a, **k):
        calls["groq"] += 1
        raise _http_error(404)

    def orr(*a, **k):
        calls["or"] += 1
        raise _http_error(402)

    monkeypatch.setattr(r, "_call_groq", groq)
    monkeypatch.setattr(r, "_call_openrouter", orr)
    for _ in range(3):
        with pytest.raises(RuntimeError, match="All AI Router providers failed"):
            r.generate_content("p")
    assert calls["or"] == 1
    assert calls["groq"] == len(r.groq_models)
    assert r.all_providers_disabled()
    assert "openrouter" in r.disabled
    disabled_msgs = [m for m in caplog.messages if "disabled for the rest" in m]
    assert len(disabled_msgs) == len(r.groq_models) + 1


def test_router_keeps_retryable_errors_enabled(monkeypatch):
    from src.ai.router import AIRouter

    r = AIRouter()
    r.keys = {"openrouter": ["k"]}
    monkeypatch.setattr(r, "_call_openrouter", lambda *a, **k: (_ for _ in ()).throw(_http_error(429)))
    with pytest.raises(RuntimeError):
        r.generate_content("p")
    assert r.disabled == {}


def test_router_status_exposes_disabled(monkeypatch):
    from src.ai import router

    r = router.AIRouter()
    r.keys = {"openrouter": ["k"]}
    r.disabled["openrouter"] = "HTTP 402"
    monkeypatch.setattr(router, "get_ai_router", lambda: r)
    status = router.get_router_status()
    assert status["disabled_providers"] == {"openrouter": "HTTP 402"}
    assert status["all_disabled"] is True


def _db(tmp_path, rows):
    from src.db.database import setup_db
    (tmp_path / "data").mkdir()
    path = tmp_path / "data" / "karriere.db"
    conn = setup_db(path)
    for i, ts in enumerate(rows):
        conn.execute(
            "INSERT INTO jobs (company, title, url, description, scraped_at) VALUES (?, ?, ?, ?, ?)",
            ("C", f"T{i}", f"https://example.org/{i}", "A job description long enough to evaluate.", ts),
        )
    conn.commit()
    conn.close()
    return path


def test_max_age_days_scopes_batch(monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    from src.ai import matcher

    now = datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"
    path = _db(tmp_path, [now.strftime(fmt), (now - timedelta(days=5)).strftime(fmt)])
    seen = []
    monkeypatch.setattr(matcher, "get_gemini_client", lambda: None)
    monkeypatch.setattr(matcher, "get_router_status", lambda: {"providers": {"groq": 1}})
    monkeypatch.setattr(matcher, "evaluate_single_job", lambda row, **k: (seen.append(row["title"]), {"gemini_status": "REJECTED_TECH_MISMATCH"})[1])
    monkeypatch.setattr(matcher.time, "sleep", lambda *_: None)

    matcher.run_gemini_matcher_on_db(rate_limit_delay=0, db_path=str(path), max_age_days=1)
    assert seen == ["T0"]
    seen.clear()
    matcher.run_gemini_matcher_on_db(rate_limit_delay=0, db_path=str(path))
    assert seen == ["T1"]  # T0 already evaluated; no max_age_days keeps old behaviour


def test_batch_aborts_when_all_providers_disabled(monkeypatch, tmp_path):
    from datetime import datetime
    from src.ai import matcher

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = _db(tmp_path, [ts] * 5)
    calls = []
    monkeypatch.setattr(matcher, "get_gemini_client", lambda: None)
    monkeypatch.setattr(matcher, "get_router_status", lambda: {"providers": {"groq": 1}, "all_disabled": True, "disabled_providers": {"groq": "HTTP 402"}})
    monkeypatch.setattr(matcher, "evaluate_single_job", lambda row, **k: (calls.append(1), None)[1])
    monkeypatch.setattr(matcher.time, "sleep", lambda *_: None)
    monkeypatch.setattr("src.core.notifier.send_telegram_alert", lambda *a, **k: True)
    monkeypatch.setattr("src.core.notifier.send_whatsapp_alert", lambda *a, **k: True)

    assert matcher.run_gemini_matcher_on_db(rate_limit_delay=0, db_path=str(path)) == []
    assert len(calls) == 1


def test_compound_words_intentionally_not_matched():
    assert prefilter_job("Teamleiter Softwareentwicklung", "") is None


def test_gemini_404_disables_only_that_model(monkeypatch):
    from src.ai.router import AIRouter

    r = AIRouter()
    r.keys = {"gemini": ["k1"]}
    bad = r.preferred_gemini_models[0]

    def call(prompt, model, key, schema=None):
        if model == bad:
            raise _http_error(404)
        return "ok"

    monkeypatch.setattr(r, "_call_gemini", call)
    assert r.generate_content("p") == "ok"
    assert r.disabled == {f"gemini/{bad}": "HTTP 404"}
    assert "gemini" in r._active_providers()


def test_gemini_multi_key_only_disabled_when_all_keys_dead(monkeypatch):
    from src.ai.router import AIRouter

    r = AIRouter()
    r.keys = {"gemini": ["k1", "k2"]}
    monkeypatch.setattr(r, "_call_gemini", lambda prompt, model, key, schema=None: (_ for _ in ()).throw(_http_error(403)))
    r._disable_on_fatal_error("gemini", "m", _http_error(403), key="k1")
    assert "gemini" not in r.disabled and r._get_next_gemini_key() == "k2"
    r._disable_on_fatal_error("gemini", "m", _http_error(403), key="k2")
    assert "gemini" in r.disabled
