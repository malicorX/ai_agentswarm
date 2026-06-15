#!/usr/bin/env bash
# Restart staging platform and wait for health before subjective verify (P10.1).
set -euo pipefail
HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"

ssh "$HOST" "systemctl restart agentswarm-platform"

for attempt in $(seq 1 15); do
  if curl -sf "${API_URL}/health" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    echo "Staging platform ready: $API_URL"
    exit 0
  fi
  sleep 2
done

echo "Staging platform did not become healthy at $API_URL" >&2
exit 1
