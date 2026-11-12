#!/usr/bin/env bash
# Open SSH tunnel to dev dashboard (port 8001) and/or prod dashboard (port 8000)
# Usage:
#   ./scripts/dev_tunnel.sh        # tunnels 8001 -> dev dashboard
#   ./scripts/dev_tunnel.sh prod   # tunnels 8000 -> prod dashboard
#   ./scripts/dev_tunnel.sh all    # tunnels both 8000 (prod) and 8001 (dev)

set -euo pipefail

TARGET="${1:-dev}"
REMOTE_HOST="oracle-server"

case "$TARGET" in
  dev)
    echo "=== Opening SSH tunnel for DEV dashboard ==="
    echo "Dev URL: http://localhost:8001 (or public: https://karriere-dev.duckdns.org)"
    echo "Press Ctrl+C to close the tunnel."
    exec ssh -N -L 8001:127.0.0.1:8001 "$REMOTE_HOST"
    ;;
  prod)
    echo "=== Opening SSH tunnel for PROD dashboard ==="
    echo "Prod URL: http://localhost:8000 (or public: https://karriere-pipeline.duckdns.org)"
    echo "Press Ctrl+C to close the tunnel."
    exec ssh -N -L 8000:127.0.0.1:8000 "$REMOTE_HOST"
    ;;
  all)
    echo "=== Opening SSH tunnel for both PROD (8000) and DEV (8001) ==="
    echo "Prod URL: http://localhost:8000"
    echo "Dev URL:  http://localhost:8001"
    echo "Press Ctrl+C to close the tunnels."
    exec ssh -N -L 8000:127.0.0.1:8000 -L 8001:127.0.0.1:8001 "$REMOTE_HOST"
    ;;
  *)
    echo "Unknown target: $TARGET. Use 'dev', 'prod', or 'all'."
    exit 1
    ;;
esac
