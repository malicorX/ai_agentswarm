#!/usr/bin/env bash
# Enable automatic pending pool-need expiry on theebie platform.
set -euo pipefail

ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
PLATFORM_SERVICE="${AGENTSWARM_PLATFORM_SERVICE:-agentswarm-platform}"
TTL_HOURS="${AGENTSWARM_POOL_NEED_MAX_AGE_HOURS:-48}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

if grep -q '^AGENTSWARM_POOL_NEED_MAX_AGE_HOURS=' "$ENV_FILE"; then
  sed -i.bak.$(date +%s) "s/^AGENTSWARM_POOL_NEED_MAX_AGE_HOURS=.*/AGENTSWARM_POOL_NEED_MAX_AGE_HOURS=${TTL_HOURS}/" "$ENV_FILE"
else
  echo "AGENTSWARM_POOL_NEED_MAX_AGE_HOURS=${TTL_HOURS}" >>"$ENV_FILE"
fi

chmod 600 "$ENV_FILE"

PORT="$(grep -E '^AGENTSWARM_PLATFORM_PORT=' "$ENV_FILE" | cut -d= -f2- || true)"
PORT="${PORT:-8010}"

systemctl restart "${PLATFORM_SERVICE}"
sleep 4
for _ in 1 2 3 4 5; do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null

PRUNE_SCRIPT="$(dirname "$0")/prune_stale_pool_needs.py"
if [[ -f "$PRUNE_SCRIPT" ]]; then
  AGENTSWARM_POOL_NEED_MAX_AGE_HOURS="$TTL_HOURS" \
    AGENTSWARM_DB="$(grep -E '^AGENTSWARM_DB=' "$ENV_FILE" | cut -d= -f2-)" \
    python3 "$PRUNE_SCRIPT"
fi

echo "Pool need TTL hardening OK (${TTL_HOURS}h)"
