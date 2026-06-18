#!/usr/bin/env bash
# Deploy AgentSwarm platform API to theebie.de (dispatch staging).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AGENTSWARM_THEEBIE_HOST:-root@theebie.de}"
REMOTE_ROOT="${AGENTSWARM_PLATFORM_REMOTE_DIR:-/opt/agentswarm}"
API_URL="${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}"

RSYNC_EXCLUDES=(
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.pytest_cache'
  --exclude '*.db'
)

ssh "$HOST" "mkdir -p '$REMOTE_ROOT/platform' '$REMOTE_ROOT/scripts/remote' '$REMOTE_ROOT/docs/infra/theebie' '$REMOTE_ROOT/docs/protocol'"

if command -v rsync >/dev/null 2>&1; then
  rsync -avz "${RSYNC_EXCLUDES[@]}" platform/ "$HOST:$REMOTE_ROOT/platform/"
  rsync -avz scripts/remote/install_platform_theebie.sh scripts/remote/bootstrap_platform_theebie.sh scripts/remote/backup_platform_db.sh scripts/remote/install_platform_backup_cron.sh scripts/remote/harden_platform_auth_theebie.sh scripts/remote/harden_platform_model_allowlist_theebie.sh scripts/remote/init_git_workspace_theebie.sh scripts/remote/install_forge_deploy_keys_theebie.sh scripts/remote/forge_git_shell.sh scripts/remote/install_optional_gitea_minio_theebie.sh "$HOST:$REMOTE_ROOT/scripts/remote/"
  rsync -avz docs/infra/theebie/ "$HOST:$REMOTE_ROOT/docs/infra/theebie/"
  rsync -avz docs/infra/windows-vm-sandbox.md "$HOST:$REMOTE_ROOT/docs/infra/"
  rsync -avz docs/protocol/capabilities.json "$HOST:$REMOTE_ROOT/docs/protocol/"
else
  scp -r platform/* "$HOST:$REMOTE_ROOT/platform/"
  scp scripts/remote/install_platform_theebie.sh scripts/remote/bootstrap_platform_theebie.sh scripts/remote/backup_platform_db.sh scripts/remote/install_platform_backup_cron.sh "$HOST:$REMOTE_ROOT/scripts/remote/"
  scp -r docs/infra/theebie/* "$HOST:$REMOTE_ROOT/docs/infra/theebie/"
  scp docs/protocol/capabilities.json "$HOST:$REMOTE_ROOT/docs/protocol/"
fi

ssh "$HOST" "chmod +x '$REMOTE_ROOT/scripts/remote/install_platform_theebie.sh' '$REMOTE_ROOT/scripts/remote/bootstrap_platform_theebie.sh' 2>/dev/null || true"
ssh "$HOST" "find '$REMOTE_ROOT/scripts/remote' -name '*.sh' -exec sed -i 's/\\r$//' {} + 2>/dev/null || true"

if [[ "${AGENTSWARM_BOOTSTRAP_PLATFORM:-1}" == "1" ]]; then
  ssh "$HOST" "bash '$REMOTE_ROOT/scripts/remote/bootstrap_platform_theebie.sh'"
fi

ssh "$HOST" "bash '$REMOTE_ROOT/scripts/remote/install_platform_theebie.sh'"

_wait_platform_ready() {
  local attempts="${1:-30}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if ssh "$HOST" "curl -sf http://127.0.0.1:8010/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "platform health check timed out after $((attempts * 2))s" >&2
  return 1
}

if [[ "${AGENTSWARM_SKIP_PLATFORM_READY_WAIT:-0}" != "1" ]]; then
  echo "Waiting for platform /health after install..."
  _wait_platform_ready 30
fi

if [[ "${AGENTSWARM_INSTALL_BACKUP_CRON:-1}" == "1" ]]; then
  ssh "$HOST" "bash '$REMOTE_ROOT/scripts/remote/install_platform_backup_cron.sh'"
fi

echo "Deployed platform API to $HOST:$REMOTE_ROOT"
echo "Public URL: ${API_URL}/health"

if [[ "${AGENTSWARM_VERIFY_STAGING_API:-1}" == "1" ]]; then
  BOOTSTRAP="$(ssh "$HOST" "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' /etc/agentswarm/platform.env 2>/dev/null | cut -d= -f2-" || true)"
  ASSIGNMENT="$(ssh "$HOST" "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' /etc/agentswarm/platform.env 2>/dev/null | cut -d= -f2-" || true)"
  MODEL_ENFORCE="$(ssh "$HOST" "grep -E '^AGENTSWARM_MODEL_ALLOWLIST_ENFORCE=' /etc/agentswarm/platform.env 2>/dev/null | cut -d= -f2-" || true)"
  export AGENTSWARM_STAGING_API_URL="$API_URL"
  export AGENTSWARM_EXPECT_DISPATCH=1
  export AGENTSWARM_EXPECT_REGISTRATION_AUTH=1
  export AGENTSWARM_VERIFY_QUICK=1
  export AGENTSWARM_BOOTSTRAP_TOKEN="$BOOTSTRAP"
  export AGENTSWARM_ASSIGNMENT_SECRET="$ASSIGNMENT"
  if [[ "$MODEL_ENFORCE" == "1" ]]; then
    export AGENTSWARM_EXPECT_MODEL_ALLOWLIST=1
  fi
  if [[ "${AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL:-0}" == "1" ]]; then
    export AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL=1
  fi
  if [[ -z "$BOOTSTRAP" ]]; then
    echo "warning: AGENTSWARM_BOOTSTRAP_TOKEN not found on $HOST; skipping post-deploy verify" >&2
  else
    python scripts/verify_production_staging.py "$API_URL"
    verify_status=$?
    if [[ $verify_status -ne 0 ]]; then
      echo "post-deploy verify failed (exit $verify_status)" >&2
      if [[ "${AGENTSWARM_DEPLOY_FAIL_ON_VERIFY:-0}" == "1" ]]; then
        exit "$verify_status"
      fi
    fi
  fi
  if [[ "${AGENTSWARM_VERIFY_DEPLOY_E2E_ENGINEERING:-0}" == "1" ]]; then
    if [[ -z "$BOOTSTRAP" || -z "$ASSIGNMENT" ]]; then
      echo "AGENTSWARM_BOOTSTRAP_TOKEN and AGENTSWARM_ASSIGNMENT_SECRET required for deploy e2e verify" >&2
      exit 1
    fi
    export AGENTSWARM_VERIFY_DEPLOY_E2E_ENGINEERING=1
    export AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL=1
    export AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN="${AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN:-1}"
    python scripts/verify_staging_deploy_e2e.py "$API_URL"
  fi
fi

if [[ "${AGENTSWARM_RECORD_STAGING_API_URL:-}" == "1" ]]; then
  python scripts/record_staging_api_url.py "$API_URL"
fi
