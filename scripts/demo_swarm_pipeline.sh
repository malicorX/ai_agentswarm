#!/usr/bin/env bash
# Federation + deploy sign-off on one local platform (credibility enabled).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e "./platform[dev]" -e "./agents" -e "./packages/sdk-python" pytest

export AGENTSWARM_REPO_ROOT="$ROOT"
export AGENTSWARM_DB="$ROOT/platform/data/swarm-pipeline-demo.db"
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

echo "Running federation demo..."
python -m agentswarm_agents.federation_demo

echo "Running deploy sign-off demo..."
python -m agentswarm_agents.deploy_demo

curl -sf "$AGENTSWARM_PLATFORM_URL/platform/summary" | python -c "
import json, sys
s = json.load(sys.stdin)
d = s.get('deploy_requests', {}).get('by_status', {})
print(f\"Platform summary: deploy pending={d.get('pending', 0)} deployed={d.get('deployed', 0)}\")
"

python -m pytest -q \
  agents/tests/test_federation_demo.py \
  agents/tests/test_deploy_demo.py \
  platform/tests/test_governance.py \
  platform/tests/test_deploy_signoff.py \
  platform/tests/test_moderation_policy.py

echo "demo_swarm_pipeline.sh complete"
