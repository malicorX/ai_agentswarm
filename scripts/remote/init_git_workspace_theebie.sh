#!/usr/bin/env bash
# Seed a shared bare git repo on theebie for distributed engineering (D0).
set -euo pipefail

ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
WORKSPACE_ROOT="${AGENTSWARM_GIT_WORKSPACE_ROOT:-/var/lib/agentswarm/git-workspaces}"
FIXTURE="${AGENTSWARM_GIT_FIXTURE:-primes}"
SSH_HOST="${AGENTSWARM_GIT_SSH_HOST:-theebie.de}"
SSH_USER="${AGENTSWARM_GIT_SSH_USER:-root}"

if [[ ! -d "$ROOT/agents" || ! -d "$ROOT/pilot/engineering-lab" ]]; then
  echo "Missing repo checkout at $ROOT — deploy platform/agents first." >&2
  exit 1
fi

mkdir -p "$WORKSPACE_ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -U pip
  "$ROOT/.venv/bin/pip" install -q -e "$ROOT/platform" -e "$ROOT/agents"
fi

export AGENTSWARM_REPO_ROOT="$ROOT"
export AGENTSWARM_GIT_WORKSPACE_ROOT="$WORKSPACE_ROOT"
export AGENTSWARM_GIT_FIXTURE="$FIXTURE"
"$ROOT/.venv/bin/python" - <<'PY'
import os
from pathlib import Path

from agentswarm_agents.engineering_workspace import init_local_git_workspace

root = Path(os.environ["AGENTSWARM_GIT_WORKSPACE_ROOT"])
fixture = os.environ.get("AGENTSWARM_GIT_FIXTURE", "primes")
init_local_git_workspace(root, fixture=fixture)
PY

BARE="${WORKSPACE_ROOT}/${FIXTURE}.git"
if [[ ! -d "$BARE" ]]; then
  echo "bare repo missing after seed: $BARE" >&2
  exit 1
fi

chmod -R ugo+rwX "$WORKSPACE_ROOT" 2>/dev/null || true

REPO_URL="${SSH_USER}@${SSH_HOST}:${BARE}"
echo "AGENTSWARM_GIT_REPO_URL=${REPO_URL}"
echo "Seeded bare repo at ${BARE}"
echo "Sparkies must git clone/push via: ${REPO_URL}"
