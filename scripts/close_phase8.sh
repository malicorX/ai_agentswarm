#!/usr/bin/env bash
# Phase 8 close-out: unit tests + dispatch smoke + volunteer subjective demo (P8.11).
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

if [[ -z "${AGENTSWARM_ASSIGNMENT_SECRET:-}" ]]; then
  ASSIGN_SECRET="$(ssh "$HOST" "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' '$ENV_FILE' | cut -d= -f2-")"
  if [[ -z "$ASSIGN_SECRET" ]]; then
    echo "Could not read AGENTSWARM_ASSIGNMENT_SECRET from $HOST:$ENV_FILE" >&2
    exit 1
  fi
  export AGENTSWARM_ASSIGNMENT_SECRET="$ASSIGN_SECRET"
fi

export AGENTSWARM_EXPECT_DISPATCH=1
python scripts/verify_dispatch_staging.py "$API_URL"

bash scripts/demo_volunteer_subjective_staging.sh --min-reviewers 1

echo "Phase 8 close-out checks OK. Tag with:"
echo "  git tag v0.9.0-phase8 && git push origin v0.9.0-phase8"
