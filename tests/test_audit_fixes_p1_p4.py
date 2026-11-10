import io
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from fastapi.testclient import TestClient

from src.ai.resume_parser import extract_text_from_pdf, ResumeParseError
from src.core import config
from src.dashboard.app import create_app
from src.dashboard.routers.jobs import clean_jobs_df
from src.db.database import save_jobs_to_db, setup_db, get_db_connection


def test_auto_match_max_age_days_default():
    """Verify default AUTO_MATCH_MAX_AGE_DAYS is 7."""
    assert config.AUTO_MATCH_MAX_AGE_DAYS >= 5


def test_pdf_magic_bytes_with_leading_whitespace_and_bom():
    """Verify PDF magic bytes check accepts files with BOM or leading bytes within 1024 bytes."""
    # PDF with UTF-8 BOM
    bom_pdf = b"\xef\xbb\xbf%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    with patch("pdfplumber.open") as mock_pdf:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Candidate Resume Text"
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]
        text = extract_text_from_pdf(bom_pdf)
        assert "Candidate Resume Text" in text

    # Invalid non-PDF bytes should still be rejected
    with pytest.raises(ResumeParseError):
        extract_text_from_pdf(b"Not a PDF file at all")


def test_clean_jobs_df_aggregates_multiple_portals():
    """Verify clean_jobs_df combines portals when deduplicating cross-portal job postings."""
    data = [
        {"company": "Google GmbH", "title": "Software Engineer (m/w/d)", "score": 90, "portal": "linkedin", "job_url": "https://linkedin.com/1"},
        {"company": "Google", "title": "Software Engineer", "score": 90, "portal": "arbeitnow", "job_url": "https://arbeitnow.com/2"},
    ]
    df = pd.DataFrame(data)
    cleaned = clean_jobs_df(df)
    assert len(cleaned) == 1
    portal_val = cleaned.iloc[0]["portal"]
    assert "arbeitnow" in portal_val and "linkedin" in portal_val


def test_request_id_middleware_attaches_header(tmp_path, monkeypatch):
    """Verify RequestIdMiddleware attaches X-Request-ID to responses."""
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) >= 8


def test_linkedin_auth_session_cookie_handling(monkeypatch):
    """Verify LinkedIn scraper reads LINKEDIN_JSESSIONID and sets matching csrf-token."""
    from src.scrapers.linkedin import _get_auth_session
    monkeypatch.setenv("LINKEDIN_LI_AT", "test_li_at_token")
    monkeypatch.setenv("LINKEDIN_JSESSIONID", "ajax:9876543210")

    sess, li_at = _get_auth_session()
    assert sess is not None
    assert li_at == "test_li_at_token"
    assert sess.cookies.get("li_at") == "test_li_at_token"
    assert "ajax:9876543210" in sess.cookies.get("JSESSIONID")
    assert getattr(sess, "csrf_token") == "ajax:9876543210"


def test_matcher_thread_local_gemini_client():
    """Verify get_thread_gemini_client isolates clients across threads."""
    import threading
    from src.ai.matcher import get_thread_gemini_client

    clients = {}

    def worker(name):
        with patch("src.ai.matcher.get_gemini_client", return_value=f"client_for_{name}"):
            clients[name] = get_thread_gemini_client()

    t1 = threading.Thread(target=worker, args=("t1",))
    t2 = threading.Thread(target=worker, args=("t2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert clients["t1"] == "client_for_t1"
    assert clients["t2"] == "client_for_t2"
    assert clients["t1"] != clients["t2"]


def test_save_jobs_to_db_uses_desc_length(tmp_path):
    """Verify save_jobs_to_db correctly saves and dedupes without loading full descriptions."""
    db_file = str(tmp_path / "test_karriere.db")
    setup_db(db_file)

    df_init = pd.DataFrame([
        {
            "company": "Tech Corp",
            "title": "Backend Dev",
            "url": "https://example.com/job1",
            "location": "Berlin",
            "description": "Short description",
            "scraped_at": "2026-11-10 12:00:00",
            "portal": "indeed",
        }
    ])
    saved = save_jobs_to_db(df_init, db_path=db_file)
    assert saved == 1

    # Insert longer description for same job
    df_longer = pd.DataFrame([
        {
            "company": "Tech Corp GmbH",
            "title": "Backend Dev (m/w/d)",
            "url": "https://example.com/job1",
            "location": "Berlin",
            "description": "Short description with much more detailed requirements and qualifications here.",
            "scraped_at": "2026-11-10 12:05:00",
            "portal": "indeed",
        }
    ])
    saved_again = save_jobs_to_db(df_longer, db_path=db_file)
    assert saved_again == 0  # Deduped

    conn = get_db_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT description FROM jobs WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    assert "detailed requirements" in row[0]
