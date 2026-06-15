#!/usr/bin/env bash
# Phase 7 close-out: unit tests + live dispatch smoke on theebie (P7.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m pytest -q platform/tests agents/tests

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"

if [[ -z "${AGENTSWARM_BOOTSTRAP_TOKEN:-}" ]]; then
  BOOTSTRAP="$(ssh "$HOST" "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' '$ENV_FILE' | cut -d= -f2-")"
  if [[ -z "$BOOTSTRAP" ]]; then
    echo "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from $HOST:$ENV_FILE" >&2
    exit 1
  fi
  export AGENTSWARM_BOOTSTRAP_TOKEN="$BOOTSTRAP"
fi

export AGENTSWARM_EXPECT_DISPATCH=1
python scripts/verify_dispatch_staging.py "$API_URL"

echo "Phase 7 close-out checks OK. Tag with:"
echo "  git tag v0.8.0-phase7 && git push origin v0.8.0-phase7"
