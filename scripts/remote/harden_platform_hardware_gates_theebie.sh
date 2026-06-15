#!/usr/bin/env bash
# Enable reviewer VRAM hardware gates on theebie.de (P9.1).
set -euo pipefail

ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
PLATFORM_SERVICE="${AGENTSWARM_PLATFORM_SERVICE:-agentswarm-platform}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

if grep -qE '^AGENTSWARM_HARDWARE_GATES_ENFORCE=' "$ENV_FILE"; then
  sed -i.bak.$(date +%s) 's/^AGENTSWARM_HARDWARE_GATES_ENFORCE=.*/AGENTSWARM_HARDWARE_GATES_ENFORCE=1/' "$ENV_FILE"
  echo "Set AGENTSWARM_HARDWARE_GATES_ENFORCE=1 in $ENV_FILE"
else
  echo "AGENTSWARM_HARDWARE_GATES_ENFORCE=1" >>"$ENV_FILE"
  echo "Appended AGENTSWARM_HARDWARE_GATES_ENFORCE=1 to $ENV_FILE"
fi

chmod 600 "$ENV_FILE"

PORT="$(grep -E '^AGENTSWARM_PLATFORM_PORT=' "$ENV_FILE" | cut -d= -f2- || true)"
PORT="${PORT:-8010}"

systemctl restart "${PLATFORM_SERVICE}"
sleep 4
for _ in 1 2 3 4 5 6 8 10; do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "Platform health check failed on 127.0.0.1:${PORT}" >&2
  exit 1
fi

ENFORCED="$(curl -sf "http://127.0.0.1:${PORT}/platform/config" | python3 -c "import sys,json; print(json.load(sys.stdin)['hardware']['enforced'])")"
echo "Local hardware.enforced=${ENFORCED}"

case "$ENFORCED" in
  True|true|1) ;;
  *)
    echo "Expected hardware.enforced=true after hardening" >&2
    exit 1
    ;;
esac

echo "Platform hardware gates hardening OK"
