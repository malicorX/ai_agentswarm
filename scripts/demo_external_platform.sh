#!/usr/bin/env bash
# Smoke-test external agent connectivity against the public platform (P5.0).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="${AGENTSWARM_PLATFORM_URL:-${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}}"

python scripts/verify_production_platform.py "$URL"
echo "External platform smoke completed against $URL"
