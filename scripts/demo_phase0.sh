#!/usr/bin/env bash
# Phase 0 end-to-end demo (macOS / Linux). Windows: use scripts/demo_phase0.ps1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -e "./platform[dev]" -e "./agents" pytest

export AGENTSWARM_REPO_ROOT="$ROOT"
export AGENTSWARM_DB="$ROOT/platform/data/demo.db"
export AGENTSWARM_PLATFORM_URL="${AGENTSWARM_PLATFORM_URL:-http://127.0.0.1:8000}"

rm -f "$AGENTSWARM_DB"

uvicorn agentswarm_platform.main:app --app-dir platform/src --host 127.0.0.1 --port 8000 &
UVICORN_PID=$!
trap 'kill $UVICORN_PID 2>/dev/null || true' EXIT

deadline=$((SECONDS + 30))
until curl -sf "$AGENTSWARM_PLATFORM_URL/health" >/dev/null; do
  if (( SECONDS > deadline )); then
    echo "Platform failed to start" >&2
    exit 1
  fi
  sleep 0.5
done

echo "Platform ready. Running phase 0 demo..."
python -m agentswarm_agents.demo

echo "Running platform tests..."
python -m pytest -q platform/tests
python -m pytest -q pilot/news-hub/tests

echo "demo_phase0.sh complete"
