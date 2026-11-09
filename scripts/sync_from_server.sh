#!/usr/bin/env bash
# Sync data/ and applications/ from Oracle Cloud server to local Mac
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REMOTE_HOST="oracle-server"
REMOTE_PATH="/opt/karriere-pipeline"
TARGET="${1:-all}"

echo "=== Syncing from ${REMOTE_HOST}:${REMOTE_PATH} (target: ${TARGET}) ==="

if [[ "$TARGET" == "all" || "$TARGET" == "data" ]]; then
  echo "--> Syncing data/..."
  rsync -avzP \
    "${REMOTE_HOST}:${REMOTE_PATH}/data/" \
    "${PROJECT_ROOT}/data/"

  echo "--> Syncing scrapers seed files..."
  rsync -avzP \
    "${REMOTE_HOST}:${REMOTE_PATH}/src/scrapers/seed_"*.json \
    "${PROJECT_ROOT}/src/scrapers/"
fi

if [[ "$TARGET" == "all" || "$TARGET" == "applications" || "$TARGET" == "--applications-only" ]]; then
  echo "--> Syncing applications/..."
  rsync -avzP \
    "${REMOTE_HOST}:${REMOTE_PATH}/applications/" \
    "${PROJECT_ROOT}/applications/"
fi

echo "=== Sync completed successfully ==="
