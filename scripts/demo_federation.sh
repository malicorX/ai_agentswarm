#!/usr/bin/env bash
# Federation end-to-end demo (macOS / Linux). Windows: scripts/demo_federation.ps1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -e "./platform[dev]" -e "./agents" -e "./packages/sdk-python" pytest

export AGENTSWARM_REPO_ROOT="$ROOT"
export AGENTSWARM_DB="$ROOT/platform/data/federation-demo.db"
export AGENTSWARM_PLATFORM_URL="${AGENTSWARM_PLATFORM_URL:-http://127.0.0.1:8000}"
export AGENTSWARM_AUTH_DISABLED=1

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

echo "Platform ready. Running federation demo..."
python -m agentswarm_agents.federation_demo

echo "Running federation-related tests..."
python -m pytest -q agents/tests/test_federation_demo.py platform/tests/test_governance.py platform/tests/test_projects.py

echo "demo_federation.sh complete"
