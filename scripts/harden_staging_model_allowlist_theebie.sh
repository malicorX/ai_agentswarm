#!/usr/bin/env bash
# Enable model allowlist enforcement on theebie.de and verify from maintainer machine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_ROOT="${AGENTSWARM_PLATFORM_REMOTE_DIR:-/opt/agentswarm}"
API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"

ssh "$HOST" "mkdir -p '$REMOTE_ROOT/scripts/remote'"
scp scripts/remote/harden_platform_model_allowlist_theebie.sh "$HOST:$REMOTE_ROOT/scripts/remote/"
ssh "$HOST" "chmod +x '$REMOTE_ROOT/scripts/remote/harden_platform_model_allowlist_theebie.sh' && bash '$REMOTE_ROOT/scripts/remote/harden_platform_model_allowlist_theebie.sh'"

BOOTSTRAP="$(ssh "$HOST" "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' '$ENV_FILE' | cut -d= -f2-")"
if [[ -z "$BOOTSTRAP" ]]; then
  echo "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from $HOST:$ENV_FILE" >&2
  exit 1
fi

export AGENTSWARM_BOOTSTRAP_TOKEN="$BOOTSTRAP"
export AGENTSWARM_EXPECT_MODEL_ALLOWLIST=1
export AGENTSWARM_EXPECT_DISPATCH=1
export AGENTSWARM_EXPECT_REGISTRATION_AUTH=1

python scripts/verify_model_allowlist_staging.py "$API_URL"
AGENTSWARM_VERIFY_QUICK=1 python scripts/verify_production_staging.py "$API_URL"

echo "Staging model allowlist hardening verified: $API_URL"
