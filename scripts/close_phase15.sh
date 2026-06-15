#!/usr/bin/env bash
# Phase 15 close-out: shell LF hygiene + staging health (P15.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m pytest -q platform/tests agents/tests

echo "Checking shell scripts (bash -n, no CRLF)..."
while IFS= read -r -d '' script; do
  bash -n "$script"
  if grep -q $'\r' "$script"; then
    echo "CRLF found in $script" >&2
    exit 1
  fi
done < <(find scripts -name '*.sh' -print0)
echo "Shell script hygiene OK"

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

export AGENTSWARM_EXPECT_LEASE_RECLAIM=1
python scripts/verify_lease_reclaim_staging.py "$API_URL"

export AGENTSWARM_STAGING_API_URL="$API_URL"
python -c "
import httpx, os, sys
url = os.environ.get('AGENTSWARM_STAGING_API_URL', '').rstrip('/')
dispatch = httpx.get(f'{url}/platform/config', timeout=30).json().get('dispatch', {})
hours = float(dispatch.get('pool_need_max_age_hours') or 0)
if hours <= 0:
    print(f'expected pool_need_max_age_hours > 0 on staging, got {hours!r}', file=sys.stderr)
    raise SystemExit(1)
print(f'Pool need TTL staging OK: pool_need_max_age_hours={hours}')
"

export AGENTSWARM_VERIFY_SUBJECTIVE_MIN_REVIEWERS=1
if [[ "${AGENTSWARM_VERIFY_SKIP_PREP:-}" != "1" ]]; then
  bash scripts/prep_staging_subjective_verify.sh
fi
for attempt in 1 2 3 4 5; do
  if python scripts/verify_volunteer_subjective_staging.py "$API_URL"; then
    break
  fi
  if [[ "$attempt" -eq 5 ]]; then
    exit 1
  fi
  echo "Subjective verify attempt $attempt failed; retrying in 15s..." >&2
  sleep 15
done

echo "Phase 15 close-out checks OK. Tag with:"
echo "  git tag v0.16.0-phase15 && git push origin v0.16.0-phase15"
