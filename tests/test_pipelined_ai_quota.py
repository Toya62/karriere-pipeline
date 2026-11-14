"""Unit tests for pipelined AI quota gating in main.py."""

from unittest.mock import MagicMock, patch
import pytest

import main


def test_check_ai_quota_single_user_mode():
    """Single-user / local mode (user_id is None) always passes quota check."""
    with patch("src.core.entitlements.check_rate_limit") as mock_crl:
        assert main._check_ai_quota(None) is True
        mock_crl.assert_not_called()


def test_check_ai_quota_with_available_quota():
    """User with remaining quota returns True."""
    mock_user = {"id": 42, "email": "test@example.com", "tier": "free"}
    with patch("src.db.database.get_user_by_id", return_value=mock_user), \
         patch("src.core.entitlements.check_rate_limit", return_value=(True, "", {"used": 5, "limit": 25})) as mock_crl:
        assert main._check_ai_quota(42) is True
        mock_crl.assert_called_once_with(mock_user, "ai_evaluations", increment=1)


def test_check_ai_quota_with_exhausted_quota():
    """User who exhausted quota returns False."""
    mock_user = {"id": 42, "email": "test@example.com", "tier": "free"}
    with patch("src.db.database.get_user_by_id", return_value=mock_user), \
         patch("src.core.entitlements.check_rate_limit", return_value=(False, "Monthly ai evaluations limit reached", {"used": 25, "limit": 25})):
        assert main._check_ai_quota(42) is False


def test_run_portal_and_ai_quota_exhausted(monkeypatch):
    """When quota is exhausted in _run_portal_and_ai:

    - run_gemini_matcher_on_db is NEVER called
    - record_usage is NEVER called
    - _alert_telegram is called
    - returned stats report quota_skipped=True and approved=0
    """
    monkeypatch.delenv("MULTI_USER_MODE", raising=False)
    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "2")

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (3,)

    with patch("src.db.database.get_db_connection", return_value=mock_conn), \
         patch("os.path.exists", return_value=True), \
         patch("main._check_ai_quota", return_value=False), \
         patch("main._alert_telegram") as mock_alert, \
         patch("src.ai.matcher.run_gemini_matcher_on_db") as mock_matcher, \
         patch("src.core.entitlements.record_usage") as mock_record:

        stats = main._run_portal_and_ai(
            "LinkedIn",
            lambda **kw: None,
            auto_ai=True,
            user_id=42,
        )

        assert stats.get("quota_skipped") is True
        assert stats.get("approved") == 0
        mock_matcher.assert_not_called()
        mock_record.assert_not_called()
        mock_alert.assert_called_once()
        alert_msg = mock_alert.call_args[0][0]
        assert "AI Quota Exhausted" in alert_msg


def test_run_portal_and_ai_quota_available(monkeypatch):
    """When quota is available in _run_portal_and_ai:

    - run_gemini_matcher_on_db is called
    - record_usage is called exactly once with 'ai_evaluations'
    - returned stats report approved count
    """
    monkeypatch.delenv("MULTI_USER_MODE", raising=False)
    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "2")

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (2,)

    fake_approved = [{"id": 1, "title": "Python Dev", "portal": "linkedin"}]

    with patch("src.db.database.get_db_connection", return_value=mock_conn), \
         patch("os.path.exists", return_value=True), \
         patch("main._check_ai_quota", return_value=True), \
         patch("main._alert_telegram") as mock_alert, \
         patch("src.ai.matcher.run_gemini_matcher_on_db", return_value=fake_approved) as mock_matcher, \
         patch("src.core.entitlements.record_usage") as mock_record:

        stats = main._run_portal_and_ai(
            "LinkedIn",
            lambda **kw: None,
            auto_ai=True,
            user_id=42,
        )

        assert stats.get("quota_skipped") is None or stats.get("quota_skipped") is False
        assert stats.get("approved") == 1
        mock_matcher.assert_called_once()
        mock_record.assert_called_once_with(42, "ai_evaluations", 1)
        mock_alert.assert_not_called()


def test_run_all_portals_pipelined_quota_exhausted(monkeypatch):
    """When quota is exhausted in _run_all_portals_pipelined:

    - matcher thread is NOT spawned / matcher is NEVER called
    - record_usage is NEVER called
    - _alert_telegram is called
    - breakdown entries report quota_skipped=True and approved=0
    """
    monkeypatch.delenv("MULTI_USER_MODE", raising=False)
    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "2")

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (5,)

    with patch("src.db.database.get_db_connection", return_value=mock_conn), \
         patch("os.path.exists", return_value=True), \
         patch("main._check_ai_quota", return_value=False), \
         patch("main._alert_telegram") as mock_alert, \
         patch("src.ai.matcher.run_gemini_matcher_on_db") as mock_matcher, \
         patch("src.core.entitlements.record_usage") as mock_record, \
         patch("src.scrapers.routing.get_portal_geo_params", return_value={}):

        p_configs = [("LinkedIn", lambda **kw: None)]
        breakdown = main._run_all_portals_pipelined(
            p_configs,
            auto_ai=True,
            user_id=42,
        )

        assert "LinkedIn" in breakdown
        assert breakdown["LinkedIn"].get("quota_skipped") is True
        assert breakdown["LinkedIn"].get("approved") == 0
        mock_matcher.assert_not_called()
        mock_record.assert_not_called()
        mock_alert.assert_called_once()
        alert_msg = mock_alert.call_args[0][0]
        assert "AI Quota Exhausted" in alert_msg


def test_run_all_portals_pipelined_quota_available(monkeypatch):
    """When quota is available in _run_all_portals_pipelined:

    - matcher thread runs run_gemini_matcher_on_db
    - record_usage is called with 'ai_evaluations'
    - breakdown reflects approved count
    """
    monkeypatch.delenv("MULTI_USER_MODE", raising=False)
    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "2")

    call_count = {"pending": 0}

    def fake_execute(query, *args, **kwargs):
        cursor = MagicMock()
        if "uj.id IS NULL" in query or "e.id IS NULL" in query:
            call_count["pending"] += 1
            cursor.fetchone.return_value = (1,) if call_count["pending"] == 1 else (0,)
        else:
            cursor.fetchone.return_value = (0,)
        return cursor

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.execute.side_effect = fake_execute

    fake_approved = [{"id": 10, "url": "https://www.linkedin.com/jobs/view/123", "title": "Dev"}]

    with patch("src.db.database.get_db_connection", return_value=mock_conn), \
         patch("os.path.exists", return_value=True), \
         patch("main._check_ai_quota", return_value=True), \
         patch("main._alert_telegram") as mock_alert, \
         patch("src.ai.matcher.run_gemini_matcher_on_db", return_value=fake_approved) as mock_matcher, \
         patch("src.core.entitlements.record_usage") as mock_record, \
         patch("src.scrapers.routing.get_portal_geo_params", return_value={}):

        p_configs = [("LinkedIn", lambda **kw: None)]
        breakdown = main._run_all_portals_pipelined(
            p_configs,
            auto_ai=True,
            user_id=42,
        )

        assert "LinkedIn" in breakdown
        assert breakdown["LinkedIn"].get("approved") == 1
        assert breakdown["LinkedIn"].get("quota_skipped") is not True
        assert mock_matcher.call_count == 1
        mock_record.assert_called_once_with(42, "ai_evaluations", 1)


def test_run_all_portals_pipelined_quota_exhausted_mid_run(monkeypatch):
    """When quota is available at start but exhausted on a later consumer-loop
    iteration, the worker stops without evaluating and without recording usage
    for the exhausted iteration.
    """
    monkeypatch.delenv("MULTI_USER_MODE", raising=False)
    monkeypatch.setenv("AUTO_MATCH_MAX_AGE_DAYS", "2")

    pending_calls = {"n": 0}

    def fake_execute(query, *args, **kwargs):
        cursor = MagicMock()
        if "uj.id IS NULL" in query or "e.id IS NULL" in query:
            pending_calls["n"] += 1
            # Always report pending jobs so the loop iterates at least twice.
            cursor.fetchone.return_value = (1,)
        else:
            cursor.fetchone.return_value = (0,)
        return cursor

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.execute.side_effect = fake_execute

    quota_results = iter([True, False])  # start OK, first loop iteration exhausted

    def fake_check_quota(uid):
        try:
            return next(quota_results)
        except StopIteration:
            return False

    fake_approved = [{"id": 10, "url": "https://www.linkedin.com/jobs/view/123", "title": "Dev"}]

    with patch("src.db.database.get_db_connection", return_value=mock_conn), \
         patch("os.path.exists", return_value=True), \
         patch("main._check_ai_quota", side_effect=fake_check_quota), \
         patch("main._alert_telegram"), \
         patch("src.ai.matcher.run_gemini_matcher_on_db", return_value=fake_approved) as mock_matcher, \
         patch("src.core.entitlements.record_usage") as mock_record, \
         patch("src.scrapers.routing.get_portal_geo_params", return_value={}):

        p_configs = [("LinkedIn", lambda **kw: None)]
        main._run_all_portals_pipelined(
            p_configs,
            auto_ai=True,
            user_id=42,
        )

        # Matcher never runs because the re-check fails before the first batch;
        # no usage is recorded.
        mock_matcher.assert_not_called()
        mock_record.assert_not_called()
