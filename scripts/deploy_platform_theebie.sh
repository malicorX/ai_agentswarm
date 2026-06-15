#!/usr/bin/env bash
# Deploy AgentSwarm platform API to theebie.de (dispatch staging).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_ROOT="${AGENTSWARM_PLATFORM_REMOTE_DIR:-/opt/agentswarm}"
API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"

RSYNC_EXCLUDES=(
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.pytest_cache'
  --exclude '*.db'
)

ssh "$HOST" "mkdir -p '$REMOTE_ROOT/platform' '$REMOTE_ROOT/scripts/remote' '$REMOTE_ROOT/docs/infra/theebie'"

if command -v rsync >/dev/null 2>&1; then
  rsync -avz "${RSYNC_EXCLUDES[@]}" platform/ "$HOST:$REMOTE_ROOT/platform/"
  rsync -avz scripts/remote/install_platform_theebie.sh scripts/remote/bootstrap_platform_theebie.sh scripts/remote/backup_platform_db.sh scripts/remote/install_platform_backup_cron.sh scripts/remote/harden_platform_auth_theebie.sh "$HOST:$REMOTE_ROOT/scripts/remote/"
  rsync -avz docs/infra/theebie/ "$HOST:$REMOTE_ROOT/docs/infra/theebie/"
else
  scp -r platform/* "$HOST:$REMOTE_ROOT/platform/"
  scp scripts/remote/install_platform_theebie.sh scripts/remote/bootstrap_platform_theebie.sh scripts/remote/backup_platform_db.sh scripts/remote/install_platform_backup_cron.sh "$HOST:$REMOTE_ROOT/scripts/remote/"
  scp -r docs/infra/theebie/* "$HOST:$REMOTE_ROOT/docs/infra/theebie/"
fi

ssh "$HOST" "chmod +x '$REMOTE_ROOT/scripts/remote/install_platform_theebie.sh' '$REMOTE_ROOT/scripts/remote/bootstrap_platform_theebie.sh' 2>/dev/null || true"

if [[ "${AGENTSWARM_BOOTSTRAP_PLATFORM:-1}" == "1" ]]; then
  ssh "$HOST" "bash '$REMOTE_ROOT/scripts/remote/bootstrap_platform_theebie.sh'"
fi

ssh "$HOST" "bash '$REMOTE_ROOT/scripts/remote/install_platform_theebie.sh'"

if [[ "${AGENTSWARM_INSTALL_BACKUP_CRON:-1}" == "1" ]]; then
  ssh "$HOST" "bash '$REMOTE_ROOT/scripts/remote/install_platform_backup_cron.sh'"
fi

echo "Deployed platform API to $HOST:$REMOTE_ROOT"
echo "Public URL: ${API_URL}/health"

if [[ "${AGENTSWARM_VERIFY_STAGING_API:-1}" == "1" ]]; then
  BOOTSTRAP="$(ssh "$HOST" "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' /etc/agentswarm/platform.env 2>/dev/null | cut -d= -f2-" || true)"
  AGENTSWARM_STAGING_API_URL="$API_URL" AGENTSWARM_EXPECT_DISPATCH=1 AGENTSWARM_VERIFY_QUICK=1 \
    AGENTSWARM_BOOTSTRAP_TOKEN="$BOOTSTRAP" \
    python scripts/verify_production_staging.py "$API_URL"
fi

if [[ "${AGENTSWARM_RECORD_STAGING_API_URL:-}" == "1" ]]; then
  python scripts/record_staging_api_url.py "$API_URL"
fi
