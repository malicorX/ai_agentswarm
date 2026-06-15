#!/usr/bin/env bash
# Volunteer subjective demo against theebie staging (P8.3).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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

export AGENTSWARM_STAGING_API_URL="$API_URL"
python scripts/demo_volunteer_subjective.py --base-url "$API_URL" "$@"
