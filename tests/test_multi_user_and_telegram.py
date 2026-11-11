"""Tests for Telegram hardening and multi-user isolation refactor."""

import os
from unittest.mock import MagicMock, patch
import urllib.error
import pytest

from src.core.notifier import send_telegram_alert, send_verification_email
from src.dashboard import state
from src.dashboard.applications import run_application_generation
from src.generators.application import _build_generation_prompt, generate_application


def test_telegram_alert_truncates_long_messages():
    """Verify that send_telegram_alert caps message length at 4000 chars."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok": true}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        long_msg = "A" * 5000
        result = send_telegram_alert(
            message=long_msg,
            bot_token="test_bot_token",
            chat_id="123456",
        )
        assert result is True
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        data = req.data.decode("utf-8")
        assert len(data) < 4500
        assert "... [Message truncated due to Telegram size limit]" in data


def test_telegram_alert_markdown_retry_on_bad_request():
    """Verify that send_telegram_alert falls back to plain text if markdown parsing fails (HTTP 400)."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        # First call raises HTTPError 400 (Bad Request: can't parse entities)
        err_fp = MagicMock()
        err_fp.read.return_value = b'{"ok": false, "description": "Bad Request: can\'t parse entities"}'
        first_error = urllib.error.HTTPError(
            url="https://api.telegram.org",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=err_fp,
        )

        # Second call succeeds
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok": true}'

        mock_urlopen.side_effect = [first_error, mock_resp]

        result = send_telegram_alert(
            message="*Unbalanced markdown _text",
            bot_token="test_bot_token",
            chat_id="123456",
            parse_mode="Markdown",
        )
        assert result is True
        assert mock_urlopen.call_count == 2
        # Second request must have parse_mode stripped
        second_req = mock_urlopen.call_args_list[1][0][0]
        assert "parse_mode" not in second_req.data.decode("utf-8")


def test_telegram_verification_token_masked_for_regular_user():
    """Verification token must not appear in Telegram alert for regular users."""
    with patch("src.core.notifier.send_resend_email", return_value=True), \
         patch("src.core.notifier.send_telegram_alert") as mock_tg:

        send_verification_email(
            email="regular_user@example.com",
            name="Regular Candidate",
            token="super_secret_token_12345",
            base_url="https://example.com",
        )
        assert mock_tg.called
        tg_message = mock_tg.call_args[0][0]
        assert "super_secret_token_12345" not in tg_message
        assert "[Delivered to user inbox]" in tg_message


def test_telegram_verification_token_included_for_admin():
    """Verification token is included in Telegram alert for admin email."""
    admin_email = os.environ.get("ADMIN_EMAIL", "pandeytoya22@gmail.com")
    with patch("src.core.notifier.send_resend_email", return_value=True), \
         patch("src.core.notifier.send_telegram_alert") as mock_tg:

        send_verification_email(
            email=admin_email,
            name="Admin User",
            token="admin_token_9999",
            base_url="https://example.com",
        )
        assert mock_tg.called
        tg_message = mock_tg.call_args[0][0]
        assert "admin_token_9999" in tg_message


def test_telegram_bot_unauthorized_when_allowed_chat_id_unset():
    """Telegram bot must reject updates when TELEGRAM_CHAT_ID is not configured."""
    from src.core.telegram_bot import process_message

    with patch("src.core.telegram_bot.ALLOWED_CHAT_ID", ""), \
         patch("src.core.telegram_bot.send_reply") as mock_reply:
        msg = {
            "chat": {"id": 999999},
            "text": "/status",
        }
        process_message(msg)
        assert mock_reply.called
        assert "Access denied" in mock_reply.call_args[0][1]


def test_multi_user_process_isolation_state():
    """Verify state tracks scraper and matcher processes separately per user_id."""
    state.USER_SCRAPER_PROCESSES.clear()
    state.USER_MATCHER_PROCESSES.clear()

    mock_proc_1 = MagicMock()
    mock_proc_2 = MagicMock()

    state.set_user_scraper_process(1, mock_proc_1)
    state.set_user_scraper_process(2, mock_proc_2)

    assert state.get_user_scraper_process(1) is mock_proc_1
    assert state.get_user_scraper_process(2) is mock_proc_2
    assert state.SCRAPER_PROCESS is mock_proc_1

    # Clearing user 2 does not affect user 1
    state.set_user_scraper_process(2, None)
    assert state.get_user_scraper_process(2) is None
    assert state.get_user_scraper_process(1) is mock_proc_1
    assert state.SCRAPER_PROCESS is mock_proc_1

    # Clean up
    state.USER_SCRAPER_PROCESSES.clear()
    state.SCRAPER_PROCESS = None


def test_build_generation_prompt_multi_tenant_vs_admin():
    """Verify prompt is dynamic for non-admin users and adheres to AGENTS.md for admin."""
    admin_prompt = _build_generation_prompt(
        company="TechCorp",
        position="Backend Engineer",
        description="Python FastAPI Postgres",
        cv_template="cv_test",
        cl_template="cl_test",
        language="en",
        agents_rules="STRICT_ADMIN_RULES",
        candidate_profile="CANDIDATE_PROFILE_DATA",
        user_id=1,
    )
    assert "Hochschule Koblenz" in admin_prompt
    assert "Bosch Werkstudent" in admin_prompt
    assert "STRICT_ADMIN_RULES" in admin_prompt

    tenant_prompt = _build_generation_prompt(
        company="TechCorp",
        position="Backend Engineer",
        description="Python FastAPI Postgres",
        cv_template="cv_test",
        cl_template="cl_test",
        language="en",
        agents_rules="GENERIC_HONESTY_RULES",
        candidate_profile="TENANT_PROFILE_DATA",
        user_id=42,
    )
    assert "Hochschule Koblenz" not in tenant_prompt
    assert "Bosch Werkstudent" not in tenant_prompt
    assert "Include all verified roles from the Candidate Profile on PAGE 1" in tenant_prompt


def test_multi_user_application_generation_path_and_git_decoupling():
    """Non-admin application generation outputs to user partitioned path and skips git sync."""
    with patch("src.generators.application._call_gemini") as mock_gemini, \
         patch("src.generators.application._compile_tex_to_pdf", side_effect=lambda p: p.replace(".tex", ".pdf")), \
         patch("src.dashboard.git_ops.git_sync_async") as mock_git_sync, \
         patch("src.dashboard.applications.register_application_in_crm"):

        mock_gemini.return_value = {
            "cv_tex": "\\documentclass{article}\\begin{document}CV\\end{document}",
            "cover_tex": "\\documentclass{article}\\begin{document}Cover\\end{document}",
            "ats_keywords_used": ["Python", "FastAPI"],
            "tailoring_summary": "Tailored for non-admin candidate",
        }

        tenant_profile = {
            "personal_info": {"name": "Alice Smith", "email": "alice@example.com", "phone": "+49 111 222333"},
            "work_experience": [{"role": "Software Developer", "company": "Alpha Tech"}],
        }

        # Run generator for user_id = 99
        result = generate_application(
            company="Startup GmbH",
            position="Python Developer",
            description="Looking for Python FastAPI developer",
            candidate_profile=tenant_profile,
            user_id=99,
            compile_pdf=True,
            clean_tex=False,
        )

        assert result["success"] is True
        cv_path = result["cv_path"]
        assert "applications/user_99/" in cv_path
        assert "applications/user_99/" in result["meta_path"]

        # Run background application generation wrapper
        run_application_generation(
            company="Startup GmbH",
            position="Python Developer",
            description="Looking for Python FastAPI developer",
            job_url="https://example.com/job",
            location="Berlin",
            language="en",
            task_key="task_test_99",
            user_id=99,
            candidate_profile=tenant_profile,
        )

        # git_sync_async must NOT be called for user_id = 99
        assert not mock_git_sync.called
