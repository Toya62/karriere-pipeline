"""Centralized SaaS tier entitlements and quota gating engine."""

from datetime import datetime, timezone
from typing import Any, Optional

from src.db.database import get_user_usage, increment_user_usage

TIER_ENTITLEMENTS: dict[str, dict[str, Any]] = {
    "free": {
        "allowed_portals": ["linkedin", "indeed"],
        "daily_scraper_runs": 1,
        "monthly_applications": 3,
        "monthly_form_copilot": 5,
        "monthly_ai_evaluations": 25,
        "monthly_ai_evaluations_byok": -1,
        "max_crm_jobs": 25,
        "allowed_lookback_days": [1],
        "custom_filter_rules": False,
        "r2_storage": False,
        "telegram_alerts": False,
    },
    "pro": {
        "allowed_portals": [
            "linkedin", "indeed", "ba", "bund", "xing",
            "personio", "ashby", "greenhouse", "arbeitnow"
        ],
        "daily_scraper_runs": 50,
        "monthly_applications": 10000,
        "monthly_form_copilot": 10000,
        "monthly_ai_evaluations": 10000,
        "monthly_ai_evaluations_byok": -1,
        "max_crm_jobs": 10000,
        "allowed_lookback_days": [1, 2, 3, 7],
        "custom_filter_rules": True,
        "r2_storage": True,
        "telegram_alerts": True,
    },
}

METRIC_PERIOD_MAP = {
    "scraper_runs": "daily",
    "applications": "monthly",
    "form_copilot": "monthly",
    "ai_evaluations": "monthly",
    "ai_evaluations_byok": "monthly",
    "crm_jobs": "cumulative",
}

METRIC_LIMIT_KEY_MAP = {
    "scraper_runs": "daily_scraper_runs",
    "applications": "monthly_applications",
    "form_copilot": "monthly_form_copilot",
    "ai_evaluations": "monthly_ai_evaluations",
    "ai_evaluations_byok": "monthly_ai_evaluations_byok",
    "crm_jobs": "max_crm_jobs",
}


def _get_period_key(cadence: str) -> str:
    now = datetime.now(timezone.utc)
    if cadence == "daily":
        return now.strftime("%Y-%m-%d")
    elif cadence == "monthly":
        return now.strftime("%Y-%m")
    return "all"


def get_user_tier(user: Optional[dict[str, Any]]) -> str:
    """Return user tier: 'pro' if admin or user['tier'] == 'pro', else 'free'."""
    if not user:
        return "free"
    if user.get("role") == "admin" or user.get("id") == 1:
        return "pro"
    return str(user.get("tier") or "free").strip().lower()


def check_feature_entitlement(user: Optional[dict[str, Any]], feature: str) -> tuple[bool, str]:
    """Check whether a user's tier has access to a specific feature or portal.
    
    Returns:
        (True, "") if entitled.
        (False, reason_string) if restricted under current tier.
    """
    tier = get_user_tier(user)
    entitlements = TIER_ENTITLEMENTS.get(tier, TIER_ENTITLEMENTS["free"])

    if feature.startswith("portal:"):
        portal = feature.split(":", 1)[1].lower().strip()
        allowed = [p.lower() for p in entitlements.get("allowed_portals", [])]
        if portal in allowed:
            return True, ""
        return False, f"Portal '{portal}' is available exclusively on the PRO plan. Upgrade to access all 9 portals."

    if feature in entitlements:
        if entitlements[feature]:
            return True, ""
        return False, f"Feature '{feature}' is a PRO exclusive capability."

    return True, ""


def check_rate_limit(
    user: Optional[dict[str, Any]],
    metric: str,
    increment: int = 0,
) -> tuple[bool, str, dict[str, int]]:
    """Evaluate whether user has remaining quota for a rate-limited metric.

    Returns:
        (True, "", stats_dict) if within limit.
        (False, error_message, stats_dict) if limit reached.
    """
    tier = get_user_tier(user)
    user_id = user.get("id", 0) if user else 0
    limit_key = METRIC_LIMIT_KEY_MAP.get(metric, metric)
    tier_conf = TIER_ENTITLEMENTS.get(tier, TIER_ENTITLEMENTS["free"])
    limit = tier_conf.get(limit_key, 10000)

    cadence = METRIC_PERIOD_MAP.get(metric, "monthly")
    period = _get_period_key(cadence)

    current_used = get_user_usage(user_id, metric, period) if user_id > 0 else 0
    total_after = current_used + increment

    stats = {
        "used": current_used,
        "limit": limit,
        "remaining": max(0, limit - current_used) if limit != -1 else -1,
    }

    # BYOK evaluations are user-funded and unmetered regardless of tier
    if metric == "ai_evaluations_byok":
        return True, "", stats

    # Pro / Admin has effectively unlimited access
    if tier == "pro":
        return True, "", stats

    if current_used >= limit or total_after > limit:
        period_label = "Daily" if cadence == "daily" else "Monthly"
        msg = (
            f"{period_label} {metric.replace('_', ' ')} limit reached ({current_used}/{limit}). "
            "Upgrade to PRO or add your own Gemini key in Settings → AI keys for unlimited access."
        )
        return False, msg, stats

    return True, "", stats


def record_usage(user_id: int, metric: str, amount: int = 1) -> int:
    """Record consumption of a rate-limited metric."""
    if user_id <= 0:
        return 0
    cadence = METRIC_PERIOD_MAP.get(metric, "monthly")
    period = _get_period_key(cadence)
    return increment_user_usage(user_id, metric, amount, period)


def get_user_usage_stats(user: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Compile a full usage and quota summary for current user session."""
    tier = get_user_tier(user)
    user_id = user.get("id", 0) if user else 0
    tier_conf = TIER_ENTITLEMENTS.get(tier, TIER_ENTITLEMENTS["free"])

    summary: dict[str, Any] = {
        "tier": tier,
        "is_pro": tier == "pro",
        "limits": tier_conf,
        "usage": {},
    }

    for metric, cadence in METRIC_PERIOD_MAP.items():
        period = _get_period_key(cadence)
        limit_key = METRIC_LIMIT_KEY_MAP.get(metric, metric)
        limit = tier_conf.get(limit_key, 10000)
        used = get_user_usage(user_id, metric, period) if user_id > 0 else 0
        summary["usage"][metric] = {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "cadence": cadence,
        }

    return summary
