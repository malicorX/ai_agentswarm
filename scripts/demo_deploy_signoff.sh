#!/usr/bin/env bash
# Deploy sign-off end-to-end demo (local platform + credibility + quorum).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e "./platform[dev]" -e "./agents" -e "./packages/sdk-python" pytest

export AGENTSWARM_REPO_ROOT="$ROOT"
export AGENTSWARM_DB="$ROOT/platform/data/deploy-demo.db"
export AGENTSWARM_PLATFORM_URL="http://127.0.0.1:8000"
export AGENTSWARM_AUTH_DISABLED=1
export AGENTSWARM_CREDIBILITY_ENABLED=1
export AGENTSWARM_CRED_INITIAL=60

rm -f "$AGENTSWARM_DB"

uvicorn agentswarm_platform.main:app --app-dir "$ROOT/platform/src" --host 127.0.0.1 --port 8000 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  if curl -sf "$AGENTSWARM_PLATFORM_URL/health" >/dev/null; then break; fi
  sleep 0.5
done

python -m agentswarm_agents.deploy_demo
python -m pytest -q agents/tests/test_deploy_demo.py platform/tests/test_deploy_signoff.py
echo "demo_deploy_signoff.sh complete"
