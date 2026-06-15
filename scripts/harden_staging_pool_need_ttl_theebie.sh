#!/usr/bin/env bash
# Set automatic pending pool-need TTL on theebie.de (P14.0).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_ROOT="${AGENTSWARM_PLATFORM_REMOTE_DIR:-/opt/agentswarm}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
TTL_HOURS="${AGENTSWARM_POOL_NEED_MAX_AGE_HOURS:-48}"

ssh "$HOST" "mkdir -p '$REMOTE_ROOT/scripts/remote'"
scp scripts/remote/harden_platform_pool_need_ttl_theebie.sh scripts/remote/prune_stale_pool_needs.py \
  "$HOST:$REMOTE_ROOT/scripts/remote/"
ssh "$HOST" "chmod +x '$REMOTE_ROOT/scripts/remote/harden_platform_pool_need_ttl_theebie.sh' && \
  AGENTSWARM_POOL_NEED_MAX_AGE_HOURS='$TTL_HOURS' \
  bash '$REMOTE_ROOT/scripts/remote/harden_platform_pool_need_ttl_theebie.sh'"

echo "Staging pool-need TTL set to ${TTL_HOURS}h on $HOST"
