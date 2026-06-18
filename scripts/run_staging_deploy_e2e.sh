#!/usr/bin/env bash
# Full staging deploy e2e: engineering goal verify + deploy sign-off chain.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_URL="${1:-${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}}"
HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"

if [[ -z "${AGENTSWARM_BOOTSTRAP_TOKEN:-}" ]]; then
  AGENTSWARM_BOOTSTRAP_TOKEN="$(ssh "$HOST" "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' '$ENV_FILE' | cut -d= -f2-" || true)"
  export AGENTSWARM_BOOTSTRAP_TOKEN
fi
if [[ -z "${AGENTSWARM_ASSIGNMENT_SECRET:-}" ]]; then
  AGENTSWARM_ASSIGNMENT_SECRET="$(ssh "$HOST" "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' '$ENV_FILE' | cut -d= -f2-" || true)"
  export AGENTSWARM_ASSIGNMENT_SECRET
fi

export AGENTSWARM_STAGING_API_URL="$API_URL"
export AGENTSWARM_VERIFY_DEPLOY_E2E_ENGINEERING=1
export AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL=1
export AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN="${AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN:-1}"

exec python scripts/verify_staging_deploy_e2e.py "$API_URL"
