#!/usr/bin/env bash
# Forced SSH command for per-goal forge deploy keys (read + push on one bare repo).
set -euo pipefail

REPO_PATH="${1:?bare repo path required}"
CMD="${SSH_ORIGINAL_COMMAND:-}"

_strip_quotes() {
  local value="$1"
  value="${value#\'}"
  value="${value%\'}"
  value="${value#\"}"
  value="${value%\"}"
  printf '%s' "$value"
}

case "$CMD" in
  git-upload-pack\ *|git-receive-pack\ *)
    op="${CMD%% *}"
    remote_path="$(_strip_quotes "${CMD#* }")"
    if [[ "$remote_path" != "$REPO_PATH" ]]; then
      echo "forge git: path mismatch (${remote_path} vs ${REPO_PATH})" >&2
      exit 1
    fi
    exec "$op" "$REPO_PATH"
    ;;
  *)
    echo "forge git: command not allowed for ${REPO_PATH}: ${CMD}" >&2
    exit 1
    ;;
esac
