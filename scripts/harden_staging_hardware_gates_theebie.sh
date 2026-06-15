#!/usr/bin/env bash
# Harden theebie staging: reviewer VRAM hardware gates (P9.1).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_ROOT="${AGENTSWARM_THEEBIE_ROOT:-/opt/agentswarm}"

scp scripts/remote/harden_platform_hardware_gates_theebie.sh "${HOST}:${REMOTE_ROOT}/scripts/remote/"
ssh "$HOST" "bash ${REMOTE_ROOT}/scripts/remote/harden_platform_hardware_gates_theebie.sh"

export AGENTSWARM_EXPECT_HARDWARE_GATES=1
export AGENTSWARM_STAGING_API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"
python scripts/verify_hardware_gates_staging.py "$AGENTSWARM_STAGING_API_URL"
