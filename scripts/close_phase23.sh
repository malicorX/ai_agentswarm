#!/usr/bin/env bash
# Phase 23 close-out: SDK config tests + weekly MCP smoke (P23.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m pytest -q platform/tests agents/tests

(
  cd packages/sdk-typescript
  npm test
)

bad=()
while IFS= read -r -d '' path; do
  if grep -q $'\r' "$path"; then
    bad+=("$path")
  fi
done < <(find scripts -name '*.sh' -print0)
if ((${#bad[@]})); then
  echo "CRLF found in shell scripts: ${bad[*]}" >&2
  exit 1
fi
while IFS= read -r -d '' path; do
  bash -n "$path"
done < <(find scripts -name '*.sh' -print0)
echo "Shell script hygiene OK"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"

if [[ -z "${AGENTSWARM_BOOTSTRAP_TOKEN:-}" ]]; then
  AGENTSWARM_BOOTSTRAP_TOKEN="$(ssh "$HOST" "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' '$ENV_FILE' | cut -d= -f2-" || true)"
  export AGENTSWARM_BOOTSTRAP_TOKEN
fi
if [[ -z "${AGENTSWARM_BOOTSTRAP_TOKEN:-}" ]]; then
  echo "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from ${HOST}:${ENV_FILE}" >&2
  exit 1
fi

export AGENTSWARM_EXPECT_DISPATCH=1
export AGENTSWARM_VERIFY_QUICK=1
unset AGENTSWARM_VERIFY_FULL
python scripts/verify_production_staging.py "$API_URL"

echo "Phase 23 close-out checks OK. Tag with:"
echo "  git tag v0.24.0-phase23 && git push origin v0.24.0-phase23"
