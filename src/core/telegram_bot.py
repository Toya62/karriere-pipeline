"""
src/core/telegram_bot.py — Interactive two-way Telegram Bot for Karriere Pipeline.
Allows controlling and monitoring pipeline from phone:
  /status  - PostgreSQL database stats, pending jobs, and container health
  /top     - Top 5 approved job matches with match score and links
  /scrape  - Trigger an immediate background scrape & match run
  /help    - List available commands
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import ssl
import subprocess
from pathlib import Path

# Ensure repo root is on sys.path
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.core.logger import get_logger
from src.core.notifier import send_telegram_alert
from src.db.database import get_db_connection, is_postgres

logger = get_logger(__name__)

# Auto-load .env
_env_path = _root / ".env"
if _env_path.exists():
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    except Exception:
        pass

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()


def send_reply(chat_id: str | int, text: str, parse_mode: str = "Markdown") -> bool:
    """Send text reply to a specific Telegram chat."""
    if not BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "KarrierePipelineBot/1.0"},
            method="POST",
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"[TelegramBot] Failed sending reply: {e}")
        return False


def handle_status() -> str:
    """Generate pipeline status report from PostgreSQL / DB."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Total jobs
        cur.execute("SELECT COUNT(*) FROM jobs;")
        total_jobs = cur.fetchone()[0]
        
        # Evaluations breakdown
        cur.execute("SELECT COUNT(*) FROM evaluations WHERE status = 'APPROVED';")
        approved_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM evaluations WHERE status != 'APPROVED';")
        rejected_count = cur.fetchone()[0]
        
        # Applications count
        cur.execute("SELECT COUNT(*) FROM applications;")
        app_count = cur.fetchone()[0]
        
        # Unevaluated jobs count
        cur.execute("""
            SELECT COUNT(*) FROM jobs j
            WHERE NOT EXISTS (
                SELECT 1 FROM evaluations e WHERE e.job_id = j.id
            );
        """)
        pending_count = cur.fetchone()[0]
        
        conn.close()
        
        backend_type = "PostgreSQL" if is_postgres() else "SQLite"
        return (
            f"📊 *Karriere Pipeline Status*\n\n"
            f"🗄️ *Database:* {backend_type}\n"
            f"📦 *Total Scraped Jobs:* {total_jobs:,}\n"
            f"⭐ *Approved Matches:* {approved_count:,}\n"
            f"🔴 *Disqualified:* {rejected_count:,}\n"
            f"⏳ *Pending AI Evaluation:* {pending_count:,}\n"
            f"📝 *Prepared Applications:* {app_count:,}\n\n"
            f"⏰ *Automated Cron:* Every 3 hrs (07:00–19:00 CET)"
        )
    except Exception as e:
        logger.error(f"[TelegramBot] /status error: {e}")
        return f"⚠️ Error querying database status: `{e}`"


def handle_top() -> str:
    """Return top 5 highest-fit approved jobs."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT j.title, j.company, j.location, e.score, j.url, e.archetype
            FROM evaluations e
            JOIN jobs j ON e.job_id = j.id
            WHERE e.status = 'APPROVED'
            ORDER BY e.score DESC, j.scraped_at DESC
            LIMIT 5;
        """)
        rows = cur.fetchall()
        conn.close()
        
        if not rows:
            return "ℹ️ No approved jobs found yet in database."
        
        lines = ["🎯 *Top 5 Job Matches:*\n"]
        for idx, (title, company, loc, score, url, arch) in enumerate(rows, 1):
            title_clean = str(title).replace("*", "").replace("_", "").strip()[:40]
            comp_clean = str(company).replace("*", "").replace("_", "").strip()[:30]
            loc_clean = str(loc or "Germany").replace("*", "").replace("_", "").strip()[:20]
            url_clean = str(url or "").strip()
            score_num = int(score) if score else 0
            
            lines.append(
                f"*{idx}. {title_clean}*\n"
                f"   🏢 {comp_clean} | 📍 {loc_clean}\n"
                f"   ⭐ Match: *{score_num}%* ({arch or 'backend'})\n"
                f"   🔗 [View Job Posting]({url_clean})\n"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[TelegramBot] /top error: {e}")
        return f"⚠️ Error querying top jobs: `{e}`"


def handle_scrape() -> str:
    """Trigger background scrape runner."""
    try:
        # Check if inside docker or on host
        runner_script = _root / "scripts" / "cron_daily_scrape.sh"
        if runner_script.exists():
            subprocess.Popen([str(runner_script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "🚀 *Scraping job started in background!*\nYou will receive a notification here once matching finishes."
        else:
            # Fallback direct CLI
            subprocess.Popen([sys.executable, "main.py", "auto", "--days", "1"], cwd=str(_root))
            return "🚀 *Scraper + AI evaluation spawned in background!*"
    except Exception as e:
        logger.error(f"[TelegramBot] /scrape trigger failed: {e}")
        return f"❌ Failed to trigger scrape: `{e}`"


def handle_help() -> str:
    return (
        "🤖 *Karriere Pipeline Interactive Assistant*\n\n"
        "Available commands:\n"
        "• `/status` — View PostgreSQL stats & pending queue\n"
        "• `/top` — Top 5 highest matching approved jobs\n"
        "• `/scrape` — Trigger an immediate scrape & AI matching batch\n"
        "• `/help` — Show this message\n"
    )


def process_message(msg: dict):
    """Route user command."""
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    
    # Strict security: Only authorized chat ID can execute commands (closed by default if unset)
    if not ALLOWED_CHAT_ID or chat_id != ALLOWED_CHAT_ID:
        logger.warning(f"[TelegramBot] Unauthorized or unconfigured command attempt from chat_id={chat_id}")
        send_reply(chat_id, "⛔ Access denied. Bot is not configured or private.")
        return
    
    text = (msg.get("text") or "").strip()
    cmd = text.split()[0].lower() if text else ""
    
    logger.info(f"[TelegramBot] Command received: '{cmd}' from chat {chat_id}")
    
    if cmd in ("/status", "/stats"):
        reply = handle_status()
    elif cmd in ("/top", "/jobs"):
        reply = handle_top()
    elif cmd == "/scrape":
        reply = handle_scrape()
    elif cmd in ("/start", "/help"):
        reply = handle_help()
    else:
        reply = f"Unknown command `{text}`. Type `/help` for options."
    
    send_reply(chat_id, reply)


def run_bot_polling():
    """Long-polling daemon loop."""
    if not BOT_TOKEN:
        logger.error("[TelegramBot] TELEGRAM_BOT_TOKEN not configured. Exiting.")
        return
    
    logger.info(f"[TelegramBot] Starting long polling daemon (Authorized Chat: {ALLOWED_CHAT_ID or 'ANY'})...")
    offset = 0
    
    ctx = ssl.create_default_context()
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            req = urllib.request.Request(url, headers={"User-Agent": "KarrierePipelineBot/1.0"})
            with urllib.request.urlopen(req, timeout=40, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = max(offset, update["update_id"] + 1)
                        if "message" in update:
                            process_message(update["message"])
        except Exception as e:
            logger.warning(f"[TelegramBot] Polling transient error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    run_bot_polling()
