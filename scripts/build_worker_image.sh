#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
TAG="${AGENTSWARM_WORKER_IMAGE:-agentswarm-worker:dev}"
echo "Building worker image: $TAG"
docker build -f docker/worker/Dockerfile -t "$TAG" .
echo "Smoke test: creative.text capsule"
printf '%s' '{"task_type":"creative.text","capsule":{"brief":"smoke test"}}' \
  | docker run --rm -i --network none "$TAG" \
  | grep -q "Container poem"
echo "Worker image ready: $TAG"
