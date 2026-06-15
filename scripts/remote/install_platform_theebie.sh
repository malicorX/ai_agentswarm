#!/usr/bin/env bash
# Run on theebie.de after deploy_platform_theebie syncs code to /opt/agentswarm.
set -euo pipefail

ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
SERVICE_NAME="${AGENTSWARM_PLATFORM_SERVICE:-agentswarm-platform}"

cd "$ROOT"

if [[ ! -f platform/pyproject.toml ]]; then
  echo "platform/pyproject.toml missing under $ROOT â€” sync code first." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  echo "Run bootstrap_platform_theebie.sh or copy docs/infra/theebie/agentswarm-platform.env.example." >&2
  exit 1
fi

if ! python3 -m venv /tmp/agentswarm-venv-check 2>/dev/null; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq python3-venv python3-pip
  else
    echo "python3-venv is required (apt install python3-venv)." >&2
    exit 1
  fi
fi
rm -rf /tmp/agentswarm-venv-check

python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ./platform

mkdir -p /var/lib/agentswarm
chmod 700 /var/lib/agentswarm

install -m 644 docs/infra/theebie/agentswarm-platform.service "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 1
PORT="$(grep -E '^AGENTSWARM_PLATFORM_PORT=' "$ENV_FILE" | cut -d= -f2- || true)"
PORT="${PORT:-8010}"
curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null
echo "Local health OK on 127.0.0.1:${PORT}"
