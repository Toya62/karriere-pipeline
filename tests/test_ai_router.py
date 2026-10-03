import json

import pandas as pd


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @staticmethod
    def read():
        return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()


def test_openai_compatible_providers_send_configured_authorization(monkeypatch):
    from src.ai.router import AIRouter
    from src.ai import router

    requests = []
    monkeypatch.setattr(router.urllib.request, "urlopen", lambda request, **kwargs: (requests.append(request), _Response())[1])
    ai_router = AIRouter()

    ai_router._call_groq("prompt", "model", "groq-secret")
    ai_router._call_openrouter("prompt", "openrouter-secret")

    assert requests[0].get_header("Authorization") == "Bearer " + "groq-secret"
    assert requests[1].get_header("Authorization") == "Bearer " + "openrouter-secret"


def test_router_status_only_reports_usable_providers(monkeypatch):
    from src.ai import router

    class ConfiguredRouter:
        keys = {"cerebras": ["configured-but-not-routed"]}
        preferred_gemini_models = ["model"]

    monkeypatch.setattr(router, "get_ai_router", lambda: ConfiguredRouter())

    assert router.get_router_status()["providers"] == {}


def test_job_matching_can_use_fallback_provider_without_gemini_key(monkeypatch, tmp_path):
    from src.ai import matcher

    input_csv = tmp_path / "jobs.csv"
    pd.DataFrame([{
        "title": "Engineer",
        "company": "Example",
        "job_url": "https://example.org/job",
        "description": "A full job description long enough to evaluate safely.",
    }]).to_csv(input_csv, index=False)
    monkeypatch.setattr(matcher, "get_gemini_client", lambda: None)
    monkeypatch.setattr(matcher, "get_router_status", lambda: {"providers": {"groq": 1}})
    monkeypatch.setattr(matcher, "evaluate_single_job", lambda *args, **kwargs: {
        "status": "APPROVED",
        "is_approved": True,
        "match_score": 80,
        "tech_stack_overlap": {},
    })
    monkeypatch.setattr(matcher, "_save_and_append_csv", lambda *args, **kwargs: None)
    monkeypatch.setattr(matcher.time, "sleep", lambda *_: None)

    approved = matcher.run_gemini_matcher(
        str(input_csv),
        output_dir=str(tmp_path / "out"),
        rate_limit_delay=0,
    )

    assert len(approved) == 1


def test_whatsapp_notifier_uses_verified_tls(monkeypatch):
    import ssl
    from src.core import notifier

    contexts = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"sent"

    def fake_urlopen(request, **kwargs):
        contexts.append(kwargs["context"])
        return Response()

    monkeypatch.setattr(notifier.urllib.request, "urlopen", fake_urlopen)

    assert notifier.send_whatsapp_alert("test", phone="+49123456789", api_key="test-key")
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname


def test_sqlite_matching_can_use_fallback_provider_without_gemini_key(monkeypatch, tmp_path):
    from src.ai import matcher
    from src.db.database import setup_db

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conn = setup_db(data_dir / "karriere.db")
    conn.execute(
        "INSERT INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)",
        ("Example", "Engineer", "https://example.org/job", "A job description long enough to evaluate safely."),
    )
    conn.commit()
    conn.close()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(matcher, "get_gemini_client", lambda: None)
    monkeypatch.setattr(matcher, "get_router_status", lambda: {"providers": {"groq": 1}})
    monkeypatch.setattr(matcher, "evaluate_single_job", lambda *args, **kwargs: {
        "gemini_status": "APPROVED",
        "gemini_score": 80,
    })
    monkeypatch.setattr(matcher, "_save_and_append_csv", lambda *args, **kwargs: None)
    monkeypatch.setattr(matcher.time, "sleep", lambda *_: None)

    approved = matcher.run_gemini_matcher_on_db(rate_limit_delay=0)

    assert len(approved) == 1


def test_strict_tls_context():
    """Verify that TLS context enforces certificate validation and hostname check."""
    import ssl
    from src.ai.router import _get_ssl_context

    ctx = _get_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode != ssl.CERT_NONE, "TLS must not allow CERT_NONE"
    assert ctx.check_hostname is True, "TLS must check hostname"


def test_sqlite_evaluations_saved_directly_without_csv(monkeypatch, tmp_path):
    from src.ai import matcher
    from src.db.database import setup_db
    import sqlite3

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conn = setup_db(data_dir / "karriere.db")
    conn.execute(
        "INSERT INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)",
        ("Test Corp", "Backend Dev", "https://example.org/test", "Long enough description for AI matching test."),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(matcher, "get_gemini_client", lambda: None)
    monkeypatch.setattr(matcher, "get_router_status", lambda: {"providers": {"groq": 1}})
    monkeypatch.setattr(matcher, "evaluate_single_job", lambda *args, **kwargs: {
        "gemini_status": "APPROVED",
        "gemini_score": 92,
        "gemini_interview_chance": "HIGH",
        "target_archetype": "backend_platform",
        "gemini_matched_skills": "Python, SQL",
        "gemini_gaps": "",
        "gemini_summary": "Great match",
        "evaluated_at": "2026-10-03 12:00:00",
    })
    monkeypatch.setattr(matcher.time, "sleep", lambda *_: None)

    approved = matcher.run_gemini_matcher_on_db(rate_limit_delay=0, db_path=str(data_dir / "karriere.db"))
    assert len(approved) == 1

    conn = sqlite3.connect(data_dir / "karriere.db")
    eval_row = conn.execute("SELECT status, score, chance FROM evaluations WHERE job_id = 1").fetchone()
    conn.close()
    assert eval_row == ("APPROVED", 92, "HIGH")

    csv_files = list(data_dir.glob("*.csv"))
    assert csv_files == []


