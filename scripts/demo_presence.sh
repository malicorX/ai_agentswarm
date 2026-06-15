#!/usr/bin/env bash
# Demo: two agents heartbeat; pool.need assigns reviewer to idle client.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AGENTSWARM_ASSIGNMENT_MODE=dispatch
export AGENTSWARM_ASSIGNMENT_SECRET=demo-dispatch-secret
export AGENTSWARM_AUTH_DISABLED=1
export AGENTSWARM_DB="${AGENTSWARM_DB:-$ROOT/platform/data/demo-presence.db}"

rm -f "$AGENTSWARM_DB"
python -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e "./platform[dev]" pytest

uvicorn agentswarm_platform.main:app --app-dir platform/src --host 127.0.0.1 --port 8010 &
UV_PID=$!
trap 'kill $UV_PID 2>/dev/null || true' EXIT
sleep 2

python - <<'PY'
import httpx

base = "http://127.0.0.1:8010"
from agentswarm_platform.crypto import generate_keypair, public_key_b64

def register(owner, caps):
    pub, _ = generate_keypair()
    r = httpx.post(
        f"{base}/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": owner,
            "capabilities": caps,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["agent_id"]

poster = register("demo-poster", ["codewriter"])
reviewer = register("demo-reviewer", ["reviewer"])
for agent_id, caps in ((poster, ["codewriter"]), (reviewer, ["reviewer"])):
    httpx.post(
        f"{base}/agents/{agent_id}/presence",
        json={"status": "idle", "capabilities": caps, "ttl_sec": 120},
        timeout=30,
    ).raise_for_status()

need = httpx.post(
    f"{base}/pool/need",
    json={
        "role": "reviewer",
        "capability_required": "reviewer",
        "task_type": "reviewer.subjective",
        "payload": {"capsule": {"brief": "demo review"}},
        "constraints": {"exclude_owners": ["demo-poster"]},
    },
    timeout=30,
)
need.raise_for_status()
body = need.json()
assert body["assigned"], body
pending = httpx.get(f"{base}/agents/{reviewer}/assignments/pending", timeout=30)
pending.raise_for_status()
assert pending.json()["task_id"] == body["task_id"]
print("demo_presence: pool assigned reviewer to idle client")
PY

echo "demo_presence.sh complete"
