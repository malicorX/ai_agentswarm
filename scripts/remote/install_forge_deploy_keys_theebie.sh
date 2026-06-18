#!/usr/bin/env bash
# Install per-goal forge deploy-key public keys for git SSH access (D1).
set -euo pipefail

ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
DB="${AGENTSWARM_DB:-/var/lib/agentswarm/agentswarm.db}"
AUTH_KEYS="${AGENTSWARM_FORGE_AUTH_KEYS:-/root/.ssh/authorized_keys}"
FORGE_SHELL="${AGENTSWARM_FORGE_GIT_SHELL:-$ROOT/scripts/remote/forge_git_shell.sh}"
MARKER_PREFIX="# agentswarm-forge:"

if [[ ! -f "$DB" ]]; then
  echo "Platform database not found: $DB" >&2
  exit 1
fi

if [[ ! -x "$FORGE_SHELL" ]]; then
  chmod +x "$FORGE_SHELL" 2>/dev/null || true
fi
if [[ ! -f "$FORGE_SHELL" ]]; then
  echo "Missing forge git shell helper: $FORGE_SHELL" >&2
  exit 1
fi

mkdir -p "$(dirname "$AUTH_KEYS")"
touch "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

export AGENTSWARM_DB="$DB"
python3 - <<'PY' > /tmp/agentswarm-forge-keys.txt
import os
import sqlite3

db = os.environ["AGENTSWARM_DB"]
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT credential_id, public_key_openssh, repo_url
    FROM goal_forge_credentials
    WHERE revoked_at IS NULL
      AND public_key_openssh IS NOT NULL
      AND TRIM(public_key_openssh) != ''
    """
).fetchall()
for row in rows:
    repo_url = str(row["repo_url"] or "").strip()
    bare_path = repo_url.split(":", 1)[-1] if ":" in repo_url else repo_url
    if not bare_path:
        continue
    print(f"{row['credential_id']}\t{row['public_key_openssh'].strip()}\t{bare_path}")
PY

added=0
while IFS=$'\t' read -r credential_id public_key bare_path; do
  [[ -z "$credential_id" || -z "$public_key" || -z "$bare_path" ]] && continue
  marker="${MARKER_PREFIX}${credential_id}"
  if grep -Fq "$marker" "$AUTH_KEYS" 2>/dev/null; then
    continue
  fi
  {
    echo "$marker"
    echo "command=\"${FORGE_SHELL} ${bare_path}\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ${public_key}"
  } >> "$AUTH_KEYS"
  added=$((added + 1))
  echo "installed ${credential_id} -> ${bare_path}"
done < /tmp/agentswarm-forge-keys.txt

rm -f /tmp/agentswarm-forge-keys.txt
echo "Forge deploy keys: ${added} added ($(wc -l < "$AUTH_KEYS") lines in ${AUTH_KEYS})"
