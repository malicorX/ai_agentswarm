#!/usr/bin/env bash
# Simulate external contributor quickstart against the public platform (P5.3).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="${AGENTSWARM_PLATFORM_URL:-${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}}"

if [[ -z "${AGENTSWARM_BOOTSTRAP_TOKEN:-}" ]]; then
  echo "Tip: set AGENTSWARM_BOOTSTRAP_TOKEN to run the maintainer enqueue + codewriter task flow."
fi

python scripts/verify_external_contributor.py "$URL"
echo "External contributor demo completed against $URL"
