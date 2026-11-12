#!/usr/bin/env bash
# ==============================================================================
# scripts/cron_daily_scrape.sh — Automated Morning Scrape & Match Runner
# Runs inside cron on Oracle VM.
# Executes pipeline in karriere-dashboard container and logs output.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${REPO_DIR}/data/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/scrape_$(date +'%Y-%m-%d_%H%M%S').log"

echo "==========================================================" | tee -a "$LOG_FILE"
echo "🚀 Karriere Pipeline — Morning Automation Triggered" | tee -a "$LOG_FILE"
echo "⏰ Time: $(date -u +'%Y-%m-%d %H:%M:%S UTC')" | tee -a "$LOG_FILE"
echo "==========================================================" | tee -a "$LOG_FILE"

# Ping healthcheck start signal if HEALTHCHECK_URL is configured
if [ -n "${HEALTHCHECK_URL:-}" ]; then
    curl -fsS -m 10 --retry 3 "${HEALTHCHECK_URL}/start" >/dev/null 2>&1 || true
fi

# Run scraper + AI match evaluation inside the running container
EXIT_CODE=0
# --user-id 1 (admin): required in multi-user mode (F15) — without it the
# scheduled run fails fast with "user_id is required in multi-user mode".
# Overlap protection comes from main.py's data/.scrape.lock (F6).
docker exec -i karriere-dashboard python main.py auto --days 1 --user-id 1 >> "$LOG_FILE" 2>&1 || EXIT_CODE=$?

# Trigger Cloudflare R2 backup on successful run
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Triggering cloud backup to Cloudflare R2..." | tee -a "$LOG_FILE"
    python3 "${REPO_DIR}/src/core/backup.py" >> "$LOG_FILE" 2>&1 || true
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Automation completed successfully at $(date -u +'%Y-%m-%d %H:%M:%S UTC')" | tee -a "$LOG_FILE"
    if [ -n "${HEALTHCHECK_URL:-}" ]; then
        curl -fsS -m 10 --retry 3 "$HEALTHCHECK_URL" >/dev/null 2>&1 || true
    fi
else
    echo "❌ Automation failed with exit code $EXIT_CODE at $(date -u +'%Y-%m-%d %H:%M:%S UTC')" | tee -a "$LOG_FILE"
    if [ -n "${HEALTHCHECK_URL:-}" ]; then
        curl -fsS -m 10 --retry 3 "${HEALTHCHECK_URL}/fail" >/dev/null 2>&1 || true
    fi
fi

# Keep only the last 14 days of log files to save disk space
find "$LOG_DIR" -name "scrape_*.log" -type f -mtime +14 -delete 2>/dev/null || true

exit $EXIT_CODE
