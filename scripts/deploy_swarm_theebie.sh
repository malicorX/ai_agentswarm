#!/usr/bin/env bash
# Deploy AgentSwarm worker swarm to theebie.de (agents + pilot + scripts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
API_URL="${AGENTSWARM_PLATFORM_URL:-${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}}"

RSYNC_EXCLUDES=(
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.pytest_cache'
  --exclude '*.db'
  --exclude 'dist'
  --exclude '.venv'
)

ssh "$HOST" "mkdir -p '$REMOTE_ROOT'/{platform,agents,pilot,scripts,docs/infra/theebie,docs/protocol,scripts/remote}"

if command -v rsync >/dev/null 2>&1; then
  rsync -avz "${RSYNC_EXCLUDES[@]}" platform/ "$HOST:$REMOTE_ROOT/platform/"
  rsync -avz "${RSYNC_EXCLUDES[@]}" agents/ "$HOST:$REMOTE_ROOT/agents/"
  rsync -avz "${RSYNC_EXCLUDES[@]}" pilot/ "$HOST:$REMOTE_ROOT/pilot/"
  rsync -avz "${RSYNC_EXCLUDES[@]}" scripts/ "$HOST:$REMOTE_ROOT/scripts/"
  rsync -avz docs/infra/theebie/ "$HOST:$REMOTE_ROOT/docs/infra/theebie/"
  rsync -avz docs/protocol/capabilities.json "$HOST:$REMOTE_ROOT/docs/protocol/"
else
  echo "rsync is required for swarm deploy" >&2
  exit 1
fi

ssh "$HOST" "chmod +x '$REMOTE_ROOT/scripts/remote/install_swarm_theebie.sh' && bash '$REMOTE_ROOT/scripts/remote/install_swarm_theebie.sh'"

echo "Deployed swarm workers to $HOST:$REMOTE_ROOT"
echo "Platform URL: ${API_URL}"

if [[ "${AGENTSWARM_VERIFY_PRODUCTION_SWARM:-1}" == "1" ]]; then
  AGENTSWARM_PLATFORM_URL="$API_URL" python3 scripts/verify_production_swarm.py "$API_URL"
fi
