"""Unit tests for Resend email dispatchers in src/core/notifier.py."""

import pytest
from unittest.mock import patch, MagicMock
from src.core.notifier import (
    send_resend_email,
    send_verification_email,
    send_welcome_email,
    send_admin_new_user_alert,
)


@patch("urllib.request.urlopen")
def test_send_resend_email_dispatches_http_post(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"id": "msg_123"}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    success = send_resend_email(
        to="candidate@example.com",
        subject="Test Subject",
        html="<p>Test Content</p>",
        api_key="re_test_key"
    )
    assert success is True
    assert mock_urlopen.called
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://api.resend.com/emails"
    assert req.headers["Authorization"] == "Bearer re_test_key"


def test_send_verification_email_renders_expected_url():
    with patch("src.core.notifier.send_resend_email", return_value=True) as mock_send:
        success = send_verification_email("user@example.com", "Alex", "tok_xyz", base_url="https://app.com")
        assert success is True
        args, kwargs = mock_send.call_args
        assert "https://app.com/api/auth/verify?token=tok_xyz" in kwargs["html"]


def test_send_welcome_email_mentions_free_and_pro():
    with patch("src.core.notifier.send_resend_email", return_value=True) as mock_send:
        success = send_welcome_email("user@example.com", "Alex")
        assert success is True
        args, kwargs = mock_send.call_args
        assert "FREE Tier" in kwargs["html"]
        assert "PRO Tier" in kwargs["html"]


def test_send_admin_new_user_alert_dispatches_alerts():
    with patch("src.core.notifier.send_telegram_alert", return_value=True) as mock_tg, \
         patch("src.core.notifier.send_resend_email", return_value=True) as mock_resend:
        user = {
            "id": 99,
            "email": "newbie@example.com",
            "full_name": "New Bie",
            "role": "candidate",
            "tier": "free",
            "auth_provider": "email",
        }
        send_admin_new_user_alert(user)
        assert mock_tg.called
        assert mock_resend.called
        tg_msg = mock_tg.call_args[0][0]
        assert "newbie@example.com" in tg_msg
        assert "New Bie" in tg_msg
