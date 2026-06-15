#!/usr/bin/env bash
# Enable owner auth on theebie platform (remove open-registration pilot flag).
set -euo pipefail

ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
SWARM_ENV="${AGENTSWARM_SWARM_ENV_FILE:-/etc/agentswarm/swarm.env}"
PLATFORM_SERVICE="${AGENTSWARM_PLATFORM_SERVICE:-agentswarm-platform}"
SWARM_SERVICE="${AGENTSWARM_SWARM_SERVICE:-agentswarm-swarm}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

require_kv() {
  local key="$1"
  if ! grep -q "^${key}=" "$ENV_FILE"; then
    echo "Missing ${key} in $ENV_FILE â€” set it before enabling auth." >&2
    exit 1
  fi
  local value
  value="$(grep -E "^${key}=" "$ENV_FILE" | cut -d= -f2-)"
  if [[ -z "$value" || "$value" == change-me* ]]; then
    echo "${key} is unset or still a placeholder in $ENV_FILE" >&2
    exit 1
  fi
}

require_kv "AGENTSWARM_SESSION_SECRET"
require_kv "AGENTSWARM_BOOTSTRAP_TOKEN"

if grep -qE '^AGENTSWARM_AUTH_DISABLED=1' "$ENV_FILE"; then
  sed -i.bak.$(date +%s) '/^AGENTSWARM_AUTH_DISABLED=1/d' "$ENV_FILE"
  echo "Removed AGENTSWARM_AUTH_DISABLED from $ENV_FILE"
elif grep -qiE '^AGENTSWARM_AUTH_DISABLED=(true|yes|on)' "$ENV_FILE"; then
  sed -i.bak.$(date +%s) '/^AGENTSWARM_AUTH_DISABLED=/d' "$ENV_FILE"
  echo "Removed AGENTSWARM_AUTH_DISABLED from $ENV_FILE"
else
  echo "AGENTSWARM_AUTH_DISABLED not set â€” auth already enforced or default"
fi

chmod 600 "$ENV_FILE"

if [[ -f "$SWARM_ENV" ]]; then
  BOOTSTRAP="$(grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
  if grep -q '^AGENTSWARM_BOOTSTRAP_TOKEN=' "$SWARM_ENV"; then
    sed -i "s/^AGENTSWARM_BOOTSTRAP_TOKEN=.*/AGENTSWARM_BOOTSTRAP_TOKEN=${BOOTSTRAP}/" "$SWARM_ENV"
  else
    echo "AGENTSWARM_BOOTSTRAP_TOKEN=${BOOTSTRAP}" >>"$SWARM_ENV"
  fi
  chmod 600 "$SWARM_ENV"
  echo "Synced bootstrap token into $SWARM_ENV"
fi

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
AUTH_ENFORCED="$(curl -sf "http://127.0.0.1:${PORT}/platform/config" | python3 -c "import sys,json; print(json.load(sys.stdin)['auth']['enforced'])")"
echo "Local auth.enforced=${AUTH_ENFORCED}"

case "$AUTH_ENFORCED" in
  True|true|1) ;;
  *)
    echo "Expected auth.enforced=true after hardening" >&2
    exit 1
    ;;
esac

if systemctl is-enabled --quiet "${SWARM_SERVICE}" 2>/dev/null; then
  systemctl restart "${SWARM_SERVICE}"
  sleep 2
  systemctl is-active --quiet "${SWARM_SERVICE}"
  echo "Restarted ${SWARM_SERVICE}"
fi

echo "Platform auth hardening OK"
