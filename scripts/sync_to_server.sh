#!/usr/bin/env bash
# Push code, data, or applications from local Mac to Oracle Cloud server (dev or prod)
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
  CONTAINER_NAME="karriere-dashboard-dev"
  DASHBOARD_URL="https://karriere-dev.duckdns.org"
else
  REMOTE_PATH="/opt/karriere-pipeline"
  CONTAINER_NAME="karriere-dashboard"
  DASHBOARD_URL="https://karriere-pipeline.duckdns.org"
fi

echo "=========================================================="
echo " Syncing to ${ENV_UPPER} (${REMOTE_HOST}:${REMOTE_PATH})"
echo " Target scope: ${TARGET} | Container: ${CONTAINER_NAME}"
echo " Live URL:     ${DASHBOARD_URL}"
echo "=========================================================="

if [[ "$TARGET" == "all" || "$TARGET" == "data" ]]; then
  echo "--> Pushing data/..."
  rsync -avzP \
    --exclude '*.db-wal' --exclude '*.db-shm' \
    "${PROJECT_ROOT}/data/" \
    "${REMOTE_HOST}:${REMOTE_PATH}/data/"
fi

if [[ "$TARGET" == "all" || "$TARGET" == "code" ]]; then
  echo "--> Pushing src/ and main.py..."
  rsync -avzP --exclude '__pycache__' --exclude '*.pyc' \
    "${PROJECT_ROOT}/src/" \
    "${REMOTE_HOST}:${REMOTE_PATH}/src/"

  rsync -avzP \
    "${PROJECT_ROOT}/main.py" \
    "${REMOTE_HOST}:${REMOTE_PATH}/main.py"

  echo "--> Pushing templates/ and AGENTS.md..."
  if [ -d "${PROJECT_ROOT}/templates" ]; then
    rsync -avzP \
      "${PROJECT_ROOT}/templates/" \
      "${REMOTE_HOST}:${REMOTE_PATH}/templates/"
  fi
  if [ -f "${PROJECT_ROOT}/AGENTS.md" ]; then
    rsync -avzP \
      "${PROJECT_ROOT}/AGENTS.md" \
      "${REMOTE_HOST}:${REMOTE_PATH}/AGENTS.md"
  fi
  if [ -f "${PROJECT_ROOT}/docker-compose.dev.yml" ]; then
    rsync -avzP \
      "${PROJECT_ROOT}/docker-compose.dev.yml" \
      "${REMOTE_HOST}:${REMOTE_PATH}/docker-compose.dev.yml"
  fi

  if [ -d "${PROJECT_ROOT}/dashboard/app" ]; then
    echo "--> Pushing dashboard/app/..."
    rsync -avzP \
      "${PROJECT_ROOT}/dashboard/app/" \
      "${REMOTE_HOST}:${REMOTE_PATH}/dashboard/app/"

    echo "--> Syncing dashboard/app into running container..."
    ssh "${REMOTE_HOST}" "docker cp ${REMOTE_PATH}/dashboard/app ${CONTAINER_NAME}:/app/dashboard/ 2>/dev/null || true"
  fi
fi

if [[ "$TARGET" == "all" || "$TARGET" == "applications" || "$TARGET" == "--applications-only" ]]; then
  echo "--> Pushing applications/..."
  rsync -avzP \
    "${PROJECT_ROOT}/applications/" \
    "${REMOTE_HOST}:${REMOTE_PATH}/applications/"
fi

echo "--> Verifying container health..."
ssh "${REMOTE_HOST}" "docker ps --filter name=${CONTAINER_NAME} --format '{{.Names}}: {{.Status}} ({{.Ports}})'"

echo "=== Sync to ${ENV_UPPER} completed successfully ==="
