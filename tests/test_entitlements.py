"""Unit tests for SaaS tier entitlements and usage quotas."""

import pytest
import uuid
from src.core.entitlements import (
    get_user_tier,
    check_feature_entitlement,
    check_rate_limit,
    record_usage,
    get_user_usage_stats,
    TIER_ENTITLEMENTS,
)


@pytest.fixture(autouse=True)
def clean_test_usage():
    from src.db.database import get_db_connection, setup_db
    setup_db()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        for uid in (99, 102, 103, 104):
            cur.execute(
                "INSERT INTO users (id, email, full_name, role, tier) VALUES (?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET tier=excluded.tier",
                (uid, f"user_{uid}@example.com", f"User {uid}", "user", "pro" if uid == 104 else "free")
            )
        cur.execute("DELETE FROM user_usage WHERE user_id >= 90")
        conn.commit()
    finally:
        conn.close()
    yield
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_usage WHERE user_id >= 90")
        cur.execute("DELETE FROM users WHERE id IN (99, 102, 103, 104)")
        conn.commit()
    finally:
        conn.close()


def test_admin_has_unlimited_pro_access():
    admin = {"id": 1, "role": "admin", "tier": "free"}
    assert get_user_tier(admin) == "pro"
    ok, _ = check_feature_entitlement(admin, "telegram_alerts")
    assert ok is True
    ok_portal, _ = check_feature_entitlement(admin, "portal:bund")
    assert ok_portal is True


def test_free_user_portal_entitlement():
    free_user = {"id": 2, "role": "user", "tier": "free"}
    assert get_user_tier(free_user) == "free"
    ok_li, _ = check_feature_entitlement(free_user, "portal:linkedin")
    ok_in, _ = check_feature_entitlement(free_user, "portal:indeed")
    assert ok_li is True
    assert ok_in is True

    ok_bund, msg = check_feature_entitlement(free_user, "portal:bund")
    assert ok_bund is False
    assert "PRO" in msg

    ok_xing, msg_xing = check_feature_entitlement(free_user, "portal:xing")
    assert ok_xing is False
    assert "PRO" in msg_xing


def test_free_user_monthly_application_limit():
    free_user = {"id": 99, "role": "user", "tier": "free"}
    # 0 used initially
    ok, _, stats = check_rate_limit(free_user, "applications")
    assert ok is True

    # Record 3 applications
    for _ in range(3):
        record_usage(99, "applications", 1)

    ok, msg, stats = check_rate_limit(free_user, "applications")
    assert ok is False
    assert stats["used"] >= 3
    assert stats["limit"] == 3
    assert "limit reached" in msg.lower()


def test_free_user_daily_scraper_limit():
    free_user = {"id": 102, "role": "user", "tier": "free"}
    ok, _, _ = check_rate_limit(free_user, "scraper_runs")
    assert ok is True

    record_usage(102, "scraper_runs", 1)
    ok, msg, stats = check_rate_limit(free_user, "scraper_runs")
    assert ok is False
    assert stats["used"] >= 1
    assert stats["limit"] == 1


def test_free_user_copilot_question_limit():
    free_user = {"id": 103, "role": "user", "tier": "free"}
    for _ in range(5):
        record_usage(103, "form_copilot", 1)
    ok, msg, stats = check_rate_limit(free_user, "form_copilot")
    assert ok is False
    assert stats["used"] >= 5
    assert stats["limit"] == 5


def test_pro_user_unlimited_quotas():
    pro_user = {"id": 104, "role": "user", "tier": "pro"}
    assert get_user_tier(pro_user) == "pro"
    ok_portal, _ = check_feature_entitlement(pro_user, "portal:bund")
    assert ok_portal is True

    # Record 100 applications
    record_usage(104, "applications", 100)
    ok, _, stats = check_rate_limit(pro_user, "applications")
    assert ok is True
