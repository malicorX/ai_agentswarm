#!/usr/bin/env bash
# One-shot prune of stale pending pool needs on theebie.de (P14.0).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_ROOT="${AGENTSWARM_PLATFORM_REMOTE_DIR:-/opt/agentswarm}"
AGE_HOURS="${AGENTSWARM_POOL_NEED_PRUNE_AGE_HOURS:-24}"

ssh "$HOST" "mkdir -p '$REMOTE_ROOT/scripts/remote'"
scp scripts/remote/prune_stale_pool_needs.py "$HOST:$REMOTE_ROOT/scripts/remote/"
ssh "$HOST" "AGENTSWARM_POOL_NEED_MAX_AGE_HOURS='$AGE_HOURS' AGENTSWARM_DB=/var/lib/agentswarm/agentswarm.db \
  /opt/agentswarm/.venv/bin/python3 '$REMOTE_ROOT/scripts/remote/prune_stale_pool_needs.py'"
