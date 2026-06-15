#!/usr/bin/env bash
# Phase 9 close-out: unit tests + dispatch + hardware gates + subjective verify (P9.11).
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

export AGENTSWARM_EXPECT_HARDWARE_GATES=1
python scripts/verify_hardware_gates_staging.py "$API_URL"

export AGENTSWARM_VERIFY_SUBJECTIVE_MIN_REVIEWERS=1
for attempt in 1 2 3; do
  if python scripts/verify_volunteer_subjective_staging.py "$API_URL"; then
    break
  fi
  if [[ "$attempt" -eq 3 ]]; then
    exit 1
  fi
  echo "Subjective verify attempt $attempt failed; retrying in 15s..." >&2
  sleep 15
done

echo "Phase 9 close-out checks OK. Tag with:"
echo "  git tag v0.10.0-phase9 && git push origin v0.10.0-phase9"
