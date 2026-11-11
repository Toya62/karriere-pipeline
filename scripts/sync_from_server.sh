#!/usr/bin/env bash
# Sync data/ and applications/ from Oracle Cloud server (dev or prod) to local Mac
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REMOTE_HOST="oracle-server"

# Determine target environment and sync scope
ARG1="${1:-}"
ARG2="${2:-}"

ENV="prod"
CURRENT_BRANCH="$(git -C "${PROJECT_ROOT}" branch --show-current 2>/dev/null || echo 'main')"
if [[ "$CURRENT_BRANCH" == "dev" || "$CURRENT_BRANCH" == "dev-"* ]]; then
  ENV="dev"
fi

TARGET="all"

if [[ "$ARG1" == "dev" || "$ARG1" == "prod" ]]; then
  ENV="$ARG1"
  TARGET="${ARG2:-all}"
elif [[ -n "$ARG1" ]]; then
  TARGET="$ARG1"
fi

ENV_UPPER=$(echo "$ENV" | tr '[:lower:]' '[:upper:]')

if [[ "$ENV" == "dev" ]]; then
  REMOTE_PATH="/opt/karriere-pipeline-dev"
else
  REMOTE_PATH="/opt/karriere-pipeline"
fi

echo "=========================================================="
echo " Syncing from ${ENV_UPPER} (${REMOTE_HOST}:${REMOTE_PATH})"
echo " Target scope: ${TARGET}"
echo "=========================================================="

if [[ "$TARGET" == "all" || "$TARGET" == "data" ]]; then
  echo "--> Syncing data/..."
  rsync -avzP \
    --exclude '*.db-wal' --exclude '*.db-shm' \
    "${REMOTE_HOST}:${REMOTE_PATH}/data/" \
    "${PROJECT_ROOT}/data/"

  echo "--> Syncing scrapers seed files..."
  rsync -avzP \
    "${REMOTE_HOST}:${REMOTE_PATH}/src/scrapers/seed_"*.json \
    "${PROJECT_ROOT}/src/scrapers/" || true
fi

if [[ "$TARGET" == "all" || "$TARGET" == "applications" || "$TARGET" == "--applications-only" ]]; then
  echo "--> Syncing applications/..."
  rsync -avzP \
    "${REMOTE_HOST}:${REMOTE_PATH}/applications/" \
    "${PROJECT_ROOT}/applications/"
fi

echo "=== Sync from ${ENV_UPPER} completed successfully ==="
