"""
src/whatsapp_notifier.py — WhatsApp notification module for Karriere Pipeline.
Supports CallMeBot API for free, zero-maintenance WhatsApp alerts with German local time (Europe/Berlin).
"""

import os
import urllib.parse
import urllib.request
import urllib.error
import ssl
from zoneinfo import ZoneInfo
from datetime import datetime
from src.core.logger import get_logger

logger = get_logger(__name__)

GERMAN_TZ = ZoneInfo("Europe/Berlin")

# ── Auto-load local .env if present ──────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
    except Exception:
        pass

def send_whatsapp_alert(message: str, phone: str = None, api_key: str = None) -> bool:
    """
    Send a WhatsApp message via CallMeBot API.

    Args:
        message (str): Text message to send. Supports basic WhatsApp markdown (*bold*, _italic_).
        phone (str, optional): Target phone number in international format (+49...). Defaults to env WHATSAPP_PHONE.
        api_key (str, optional): CallMeBot API key. Defaults to env CALLMEBOT_API_KEY.

    Returns:
        bool: True if notification was sent successfully, False otherwise.
    """
    target_phone = phone or os.environ.get("WHATSAPP_PHONE")
    if not target_phone:
        logger.warning(
            "[WhatsApp] WHATSAPP_PHONE not configured. Alert suppressed. "
            "To activate WhatsApp alerts, set WHATSAPP_PHONE in your environment or .env file."
        )
        return False

    target_phone = target_phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not target_phone.startswith("+"):
        target_phone = "+" + target_phone

    key = api_key or os.environ.get("CALLMEBOT_API_KEY")

    if not key:
        logger.warning(
            "[WhatsApp] CALLMEBOT_API_KEY not configured. Alert suppressed. "
            "To activate WhatsApp alerts, set CALLMEBOT_API_KEY and WHATSAPP_PHONE in your environment or GitHub Secrets."
        )
        return False

    encoded_msg = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={target_phone}&text={encoded_msg}&apikey={key}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as resp:
            body = resp.read().decode("utf-8")
            if resp.status == 200:
                logger.info(f"[WhatsApp] Alert successfully dispatched to {target_phone}")
                return True
            else:
                logger.error(f"[WhatsApp] CallMeBot API returned HTTP {resp.status}: {body}")
                return False
    except Exception as e:
        logger.error(f"[WhatsApp] Connection error when sending WhatsApp alert: {e}")
        return False


def notify_scrape_summary(
    new_jobs_count: int = 0,
    approved_count: int = 0,
    portal: str = "all",
    run_approved_count: int = 0,
    run_new_count: int = 0,
    portal_breakdown: dict = None
) -> bool:
    """Format and send a structured scrape & match notification with German Local Time (CEST/CET)."""
    dashboard_url = "https://YOUR_GITHUB_USERNAME.github.io/karriere-pipeline/"
    german_time_str = datetime.now(GERMAN_TZ).strftime("%d.%m.%Y, %H:%M CEST")

    breakdown_lines = []
    if portal_breakdown:
        for p_name, p_stats in portal_breakdown.items():
            p_app = p_stats.get("approved", 0)
            p_scr = p_stats.get("scraped", 0)
            breakdown_lines.append(f"   • {p_name}: +{p_app} approved ({p_scr} scraped)")

    breakdown_text = ("\n" + "\n".join(breakdown_lines) + "\n") if breakdown_lines else "\n"

    msg = (
        f"🚀 *Karriere Pipeline — Scrape Complete*\n\n"
        f"⏰ *Batch Time:* {german_time_str} ({portal.upper()})\n"
        f"✨ *New Approved (This Run):* +{run_approved_count}\n"
        f"📦 *Total Scraped (This Run):* +{run_new_count}"
        f"{breakdown_text}\n"
        f"⭐ *AI Approved (Today):* {approved_count}\n"
        f"📊 *Total Scraped (Today):* {new_jobs_count}\n\n"
        f"🌐 *Open Dashboard:* {dashboard_url}"
    )
    return send_whatsapp_alert(msg)


if __name__ == "__main__":
    test_time = datetime.now(GERMAN_TZ).strftime("%d.%m.%Y, %H:%M CEST")
    test_msg = f"🔔 *Test Alert from Karriere Pipeline*\n\nGerman Time Synchronization Active: *{test_time}*"
    target = os.environ.get("WHATSAPP_PHONE")
    print(f"Testing WhatsApp dispatch with phone: {target or '[Not set - check .env]'}")
    success = send_whatsapp_alert(test_msg)
    if not success:
        print("Note: Set WHATSAPP_PHONE and CALLMEBOT_API_KEY in your .env or GitHub secrets to enable live messaging.")
