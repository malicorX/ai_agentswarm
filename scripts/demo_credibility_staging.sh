#!/usr/bin/env bash
# Verify credibility spec parameters on the public staging platform (P5.4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="${AGENTSWARM_PLATFORM_URL:-${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}}"

python scripts/verify_credibility_staging.py "$URL"
echo "Credibility staging verify completed against $URL"
