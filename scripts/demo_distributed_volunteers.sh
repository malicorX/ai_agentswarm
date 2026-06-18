#!/usr/bin/env bash
# Distributed volunteer demo: sparky1 + sparky2 + this machine against staging.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"
SPARKY1="${AGENTSWARM_SPARKY1_HOST:-sparky1}"
SPARKY2="${AGENTSWARM_SPARKY2_HOST:-sparky2}"
DIST_REPO="${AGENTSWARM_DIST_REPO:-~/ai_agentSwarm}"
SYNC_REMOTES=0

usage() {
  echo "Usage: $0 [--sync-remotes] [demo_distributed_volunteers.py args...]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sync-remotes)
      SYNC_REMOTES=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      break
      ;;
  esac
done

sync_remote() {
  local remote="$1"
  echo "Syncing repo to ${remote}:${DIST_REPO} ..."
  ssh "$remote" "mkdir -p $DIST_REPO/scripts"
  scp -r agents platform "${remote}:${DIST_REPO}/"
  scp scripts/demo_volunteer_subjective.py scripts/run_volunteer_role.py scripts/demo_distributed_volunteers.py "${remote}:${DIST_REPO}/scripts/"
  ssh "$remote" "cd $DIST_REPO && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q -e platform -e agents"
}

if [[ -z "${AGENTSWARM_BOOTSTRAP_TOKEN:-}" ]]; then
  AGENTSWARM_BOOTSTRAP_TOKEN="$(ssh "$HOST" "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $ENV_FILE | cut -d= -f2-")"
  export AGENTSWARM_BOOTSTRAP_TOKEN
fi
if [[ -z "${AGENTSWARM_ASSIGNMENT_SECRET:-}" ]]; then
  AGENTSWARM_ASSIGNMENT_SECRET="$(ssh "$HOST" "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' $ENV_FILE | cut -d= -f2-")"
  export AGENTSWARM_ASSIGNMENT_SECRET
fi

export AGENTSWARM_SPARKY1_HOST="$SPARKY1"
export AGENTSWARM_SPARKY2_HOST="$SPARKY2"
export AGENTSWARM_DIST_REPO="$DIST_REPO"
export AGENTSWARM_STAGING_API_URL="$API_URL"

if [[ "$SYNC_REMOTES" -eq 1 ]]; then
  sync_remote "$SPARKY1"
  sync_remote "$SPARKY2"
else
  for remote in "$SPARKY1" "$SPARKY2"; do
    if ! ssh "$remote" "test -x $DIST_REPO/.venv/bin/python"; then
      echo "Remote venv missing on ${remote}:${DIST_REPO}. Re-run with --sync-remotes." >&2
      exit 1
    fi
  done
fi

exec python3 scripts/demo_distributed_volunteers.py --base-url "$API_URL" "$@"
