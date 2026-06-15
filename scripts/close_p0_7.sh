#!/usr/bin/env bash
# P0.7 close-out: verify Pages + record URL in docs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-https://malicorx.github.io/ai_agentswarm}"
cd "$ROOT"
python scripts/close_p0_7.py "$URL"
