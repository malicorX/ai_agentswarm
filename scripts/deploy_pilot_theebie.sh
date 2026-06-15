#!/usr/bin/env bash
# Deploy staged pilot static site to theebie.de (under /sites/agentswarm/, not moltworld).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_DIR="${AGENTSWARM_THEEBIE_DIR:-/var/www/html/sites/agentswarm}"
STAGING="${AGENTSWARM_PILOT_STAGING_DIR:-$ROOT/dist/pilot-site}"
TARGET_URL="${AGENTSWARM_DEPLOY_TARGET_URL:-https://theebie.de/sites/agentswarm}"

python scripts/stage_pilot_site.py --output "$STAGING"

ssh "$HOST" "mkdir -p '$REMOTE_DIR'"
if command -v rsync >/dev/null 2>&1; then
  rsync -avz --delete "$STAGING/" "$HOST:$REMOTE_DIR/"
else
  ssh "$HOST" "rm -rf '$REMOTE_DIR'/*"
  scp -r "$STAGING"/* "$HOST:$REMOTE_DIR/"
fi

echo "Deployed pilot site to $HOST:$REMOTE_DIR"
echo "Live URL: $TARGET_URL/"

if [[ "${AGENTSWARM_RECORD_PILOT_URL:-}" == "1" ]]; then
  python scripts/record_pilot_url.py "$TARGET_URL"
fi
