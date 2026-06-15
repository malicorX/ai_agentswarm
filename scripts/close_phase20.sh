#!/usr/bin/env bash
# Phase 20 close-out: SDK dispatch e2e + staging verify (P20.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m pytest -q platform/tests agents/tests
python -m pytest -q platform/tests/test_sdk_dispatch.py

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

(
  cd packages/sdk-typescript
  npm run test
)

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

python scripts/verify_sdk_dispatch_staging.py "$API_URL"

echo "Phase 20 close-out checks OK. Tag with:"
echo "  git tag v0.21.0-phase20 && git push origin v0.21.0-phase20"
