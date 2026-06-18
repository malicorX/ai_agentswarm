#!/usr/bin/env bash
# Optional Gitea + MinIO for demos (D3). Idempotent docker compose up.
set -euo pipefail

REMOTE_ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
COMPOSE_FILE="${REMOTE_ROOT}/docs/infra/theebie/docker-compose.optional-gitea-minio.yml"
DATA_ROOT="${AGENTSWARM_OPTIONAL_FORGE_DATA:-/var/lib/agentswarm/optional-forge}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

mkdir -p "$DATA_ROOT/gitea" "$DATA_ROOT/minio"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

export AGENTSWARM_OPTIONAL_FORGE_DATA="$DATA_ROOT"
docker compose -f "$COMPOSE_FILE" up -d

echo "Gitea:  http://127.0.0.1:3000 (map via Caddy if needed)"
echo "MinIO:  http://127.0.0.1:9000 (API) / :9001 (console)"
echo "Data:   $DATA_ROOT"
