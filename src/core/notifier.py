"""
src/core/notifier.py — Notification module for Karriere Pipeline.
Supports Telegram Bot API for real-time alerts with German local time (Europe/Berlin).
"""

import os
import sys
import json
import urllib.parse
import urllib.request
import urllib.error
import ssl
from zoneinfo import ZoneInfo
from datetime import datetime
from pathlib import Path

# ── Ensure workspace root is in sys.path when executed directly ──────────────
_root_dir = Path(__file__).resolve().parent.parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from src.core.logger import get_logger

logger = get_logger(__name__)

GERMAN_TZ = ZoneInfo("Europe/Berlin")

# ── Auto-load local .env if present ──────────────────────────────────────────
from pathlib import Path
_root_dir = Path(__file__).resolve().parent.parent.parent
_env_path = os.path.join(_root_dir, ".env")
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


def send_telegram_alert(message: str, bot_token: str = None, chat_id: str = None, parse_mode: str = "Markdown") -> bool:
    """
    Send a message via Telegram Bot API.

    Args:
        message (str): Text message to send. Supports Markdown or HTML.
        bot_token (str, optional): Telegram Bot token. Defaults to TELEGRAM_BOT_TOKEN env.
        chat_id (str, optional): Target chat ID. Defaults to TELEGRAM_CHAT_ID env.
        parse_mode (str): Markdown or HTML parsing mode.

    Returns:
        bool: True if alert dispatched successfully, False otherwise.
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    target_chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not target_chat:
        logger.warning(
            "[Telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured. Alert suppressed. "
            "To activate Telegram alerts, set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env or environment."
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(target_chat).strip(),
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "KarrierePipeline/2.0"},
            method="POST",
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            if resp.status == 200:
                logger.info(f"[Telegram] Alert successfully dispatched to chat {target_chat}")
                return True
            else:
                logger.error(f"[Telegram] Telegram Bot API returned HTTP {resp.status}: {body}")
                return False
    except Exception as e:
        logger.error(f"[Telegram] Connection error when sending Telegram alert: {e}")
        return False


# Backward compatibility alias for transition
send_alert = send_telegram_alert
send_whatsapp_alert = send_telegram_alert


def notify_scrape_summary(
    new_jobs_count: int = 0,
    approved_count: int = 0,
    portal: str = "all",
    run_approved_count: int = 0,
    run_new_count: int = 0,
    portal_breakdown: dict = None,
    suppress_empty: bool = True,
) -> bool:
    """Format and send a structured scrape & match notification with German Local Time (CEST/CET)."""
    if suppress_empty and run_approved_count == 0 and run_new_count == 0:
        logger.info("[Telegram] Zero fresh jobs and zero approved in this run; summary alert suppressed.")
        return True

    german_time_str = datetime.now(GERMAN_TZ).strftime("%d.%m.%Y, %H:%M CEST")

    breakdown_lines = []
    if portal_breakdown:
        for p_name, p_stats in portal_breakdown.items():
            if p_stats.get("error"):
                breakdown_lines.append(f"   • {p_name}: ⚠️ Error (failed)")
            else:
                p_app = p_stats.get("approved", 0)
                p_scr = p_stats.get("scraped", 0)
                breakdown_lines.append(f"   • {p_name}: +{p_app} approved ({p_scr} fresh)")

    breakdown_text = ("\n" + "\n".join(breakdown_lines) + "\n") if breakdown_lines else "\n"

    msg = (
        f"🚀 *Karriere Pipeline — Scrape Complete*\n\n"
        f"⏰ *Batch Time:* {german_time_str} ({portal.upper()})\n"
        f"✨ *New Approved (This Run):* +{run_approved_count}\n"
        f"📦 *Total Scraped (This Run):* +{run_new_count}"
        f"{breakdown_text}\n"
        f"⭐ *AI Approved (Today):* {approved_count}\n"
        f"📊 *Total Scraped (Today):* {new_jobs_count}"
    )
    return send_telegram_alert(msg)


# ── Resend Email Dispatchers ─────────────────────────────────────────────────

def send_resend_email(
    to: str | list[str],
    subject: str,
    html: str,
    from_addr: str = None,
    api_key: str = None,
) -> bool:
    """Send transactional email via Resend REST API."""
    key = api_key or os.environ.get("RESEND_API_KEY")
    sender = from_addr or os.environ.get("RESEND_FROM_EMAIL", "Karriere Pipeline <onboarding@resend.dev>")

    if not key:
        logger.warning("[Resend] RESEND_API_KEY not configured. Email suppressed.")
        return False

    recipients = [to] if isinstance(to, str) else list(to)
    payload = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html,
    }

    url = "https://api.resend.com/emails"
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "KarrierePipeline/2.0",
            },
            method="POST",
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            if resp.status in (200, 201):
                logger.info(f"[Resend] Email successfully sent to {recipients}: subject='{subject}'")
                return True
            else:
                logger.error(f"[Resend] API returned HTTP {resp.status}: {body}")
                return False
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="replace") if hasattr(he, "read") else ""
        logger.error(f"[Resend] HTTP {he.code} sending to {recipients}: {err_body}")
        return False
    except Exception as e:
        logger.error(f"[Resend] Error sending email to {recipients}: {e}")
        return False


def send_verification_email(
    email: str,
    name: str,
    token: str,
    base_url: str = None,
) -> bool:
    """Send magic verification link to newly registered user."""
    app_url = (base_url or os.environ.get("APP_BASE_URL", "https://karriere.pandeytoya.me")).rstrip("/")
    verify_url = f"{app_url}/api/auth/verify?token={token}"
    display_name = (name or "").strip() or "there"

    subject = "Verify your email — Karriere Pipeline"
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 540px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }}
    .logo {{ font-size: 20px; font-weight: bold; color: #38bdf8; margin-bottom: 24px; }}
    h1 {{ font-size: 22px; color: #f8fafc; margin-top: 0; }}
    p {{ font-size: 15px; line-height: 1.6; color: #cbd5e1; }}
    .btn {{ display: inline-block; background: linear-gradient(135deg, #2563eb, #38bdf8); color: #ffffff !important; font-weight: 600; text-decoration: none; padding: 12px 28px; border-radius: 8px; margin: 20px 0; }}
    .footer {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid #334155; padding-top: 16px; }}
    .fallback {{ font-size: 13px; color: #94a3b8; word-break: break-all; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🚀 Karriere Pipeline</div>
    <h1>Verify Your Email Address</h1>
    <p>Hi {display_name},</p>
    <p>Thank you for registering on Karriere Pipeline. Please confirm your email address by clicking the button below:</p>
    <div style="text-align: center;">
      <a href="{verify_url}" class="btn" target="_blank">Verify Email & Activate Account</a>
    </div>
    <p class="fallback">Or paste this link into your browser:<br/><a href="{verify_url}" style="color: #38bdf8;">{verify_url}</a></p>
    <p class="footer">This link expires in 24 hours. If you did not sign up for Karriere Pipeline, you can safely ignore this email.</p>
  </div>
</body>
</html>"""
    return send_resend_email(to=email, subject=subject, html=html)


def send_welcome_email(email: str, name: str) -> bool:
    """Send welcome onboarding email detailing Free vs Pro tier benefits."""
    display_name = (name or "").strip() or "there"
    subject = "Welcome to Karriere Pipeline — Your AI Job Search Copilot"
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; }}
    .card {{ max-width: 580px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }}
    .logo {{ font-size: 20px; font-weight: bold; color: #38bdf8; margin-bottom: 24px; }}
    h1 {{ font-size: 22px; color: #f8fafc; margin-top: 0; }}
    p {{ font-size: 15px; line-height: 1.6; color: #cbd5e1; }}
    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #334155; }}
    th {{ color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 12px; }}
    .pro-highlight {{ color: #fbbf24; font-weight: bold; }}
    .footer {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid #334155; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🚀 Karriere Pipeline</div>
    <h1>Welcome aboard, {display_name}!</h1>
    <p>Your account is activated and ready. You are currently on the <strong>FREE Tier</strong>, with instant access to autonomous job intelligence.</p>
    
    <table>
      <thead>
        <tr>
          <th>Capability</th>
          <th>FREE Tier</th>
          <th class="pro-highlight">PRO Tier</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Job Portals</td>
          <td>LinkedIn, Indeed</td>
          <td class="pro-highlight">All 9 Portals (+BA, Xing, Bund, etc.)</td>
        </tr>
        <tr>
          <td>Daily Scraper Runs</td>
          <td>1 run / day (24h)</td>
          <td class="pro-highlight">Unlimited (24h, 48h, 7d, 30d)</td>
        </tr>
        <tr>
          <td>AI Scoring & Matching</td>
          <td>Rule pre-filter + 25 AI/mo</td>
          <td class="pro-highlight">Deep AI Match Analysis</td>
        </tr>
        <tr>
          <td>Tailored PDF Packages</td>
          <td>3 / month</td>
          <td class="pro-highlight">Unlimited ATS Packages</td>
        </tr>
      </tbody>
    </table>

    <p>Ready to get started? Upload your master resume in the Candidate Profile to begin tailored job discovery.</p>
    <p class="footer">Karriere Pipeline • Autonomous Job Search & Application Intelligence</p>
  </div>
</body>
</html>"""
    return send_resend_email(to=email, subject=subject, html=html)


def send_admin_new_user_alert(user: dict) -> None:
    """Notify admin via Telegram and Resend email on new user registration."""
    email = user.get("email", "unknown")
    full_name = user.get("full_name") or "Unnamed"
    auth_provider = user.get("auth_provider", "email")
    tier = user.get("tier", "free")
    user_id = user.get("id", "N/A")

    german_time = datetime.now(GERMAN_TZ).strftime("%d.%m.%Y, %H:%M CEST")

    # 1. Telegram alert
    tg_msg = (
        f"👤 *New User Registered*\n\n"
        f"• *ID:* `{user_id}`\n"
        f"• *Name:* {full_name}\n"
        f"• *Email:* `{email}`\n"
        f"• *Provider:* {auth_provider}\n"
        f"• *Tier:* `{tier}`\n"
        f"• *Time:* {german_time}\n"
    )
    try:
        send_telegram_alert(tg_msg)
    except Exception as e:
        logger.error(f"[Alert] Failed to send Telegram admin alert: {e}")

    # 2. Resend email alert to admin
    admin_recipient = os.environ.get("ADMIN_ALERT_EMAIL", "pandey.ramu62@gmail.com")
    email_html = f"""<div style="font-family: sans-serif; padding: 16px; background: #0f172a; color: #f8fafc; border-radius: 8px;">
      <h2 style="color: #38bdf8;">👤 New User Registered</h2>
      <p>A new user has joined Karriere Pipeline:</p>
      <ul>
        <li><strong>ID:</strong> {user_id}</li>
        <li><strong>Name:</strong> {full_name}</li>
        <li><strong>Email:</strong> {email}</li>
        <li><strong>Provider:</strong> {auth_provider}</li>
        <li><strong>Tier:</strong> {tier}</li>
        <li><strong>Registered At:</strong> {german_time}</li>
      </ul>
    </div>"""
    try:
        send_resend_email(
            to=admin_recipient,
            subject=f"New User Registered: {email}",
            html=email_html,
        )
    except Exception as e:
        logger.error(f"[Alert] Failed to send Resend admin alert: {e}")



if __name__ == "__main__":
    test_time = datetime.now(GERMAN_TZ).strftime("%d.%m.%Y, %H:%M CEST")
    test_msg = f"🔔 *Test Alert from Karriere Pipeline*\n\nGerman Time Synchronization Active: *{test_time}*"
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    print(f"Testing Telegram dispatch with token: {'[Set]' if token else '[Not set]'}, chat: {chat or '[Not set]'}")
    success = send_telegram_alert(test_msg)
    if not success:
        print("Note: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env or environment to enable live alerts.")
