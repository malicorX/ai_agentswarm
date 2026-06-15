#!/usr/bin/env bash
# Install AgentSwarm worker swarm on theebie.de (P5.1).
set -euo pipefail

ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
PLATFORM_ENV="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
SWARM_ENV="${AGENTSWARM_SWARM_ENV_FILE:-/etc/agentswarm/swarm.env}"
SERVICE_NAME="${AGENTSWARM_SWARM_SERVICE:-agentswarm-swarm}"

cd "$ROOT"

for path in agents/pyproject.toml pilot/index.html scripts/deploy_pilot_theebie.sh; do
  if [[ ! -e "$path" ]]; then
    echo "Missing $ROOT/$path — run deploy_swarm_theebie.sh first." >&2
    exit 1
  fi
done

python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ./platform -e ./agents

mkdir -p /etc/agentswarm
if [[ ! -f "$SWARM_ENV" ]]; then
  if [[ ! -f "$PLATFORM_ENV" ]]; then
    echo "Missing $PLATFORM_ENV — bootstrap platform first." >&2
    exit 1
  fi
  BOOTSTRAP="$(grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' "$PLATFORM_ENV" | cut -d= -f2- || true)"
  if [[ -z "$BOOTSTRAP" ]]; then
    echo "AGENTSWARM_BOOTSTRAP_TOKEN not found in $PLATFORM_ENV" >&2
    exit 1
  fi
  sed "s/copy-from-etc-agentswarm-platform-env/$BOOTSTRAP/" \
    docs/infra/theebie/agentswarm-swarm.env.example >"$SWARM_ENV"
  chmod 600 "$SWARM_ENV"
  echo "Created $SWARM_ENV"
fi

install -m 644 docs/infra/theebie/agentswarm-swarm.service "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 2
systemctl is-active --quiet "${SERVICE_NAME}"
echo "Swarm service active: ${SERVICE_NAME}"
