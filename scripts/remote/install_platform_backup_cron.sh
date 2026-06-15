#!/usr/bin/env bash
# Install daily SQLite backup cron for AgentSwarm platform on theebie.de.
set -euo pipefail

ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
CRON_FILE="/etc/cron.d/agentswarm-platform-backup"
BACKUP_SCRIPT="${ROOT}/scripts/remote/backup_platform_db.sh"

if [[ ! -f "$BACKUP_SCRIPT" ]]; then
  echo "Missing $BACKUP_SCRIPT â€” sync platform deploy first." >&2
  exit 1
fi

chmod +x "$BACKUP_SCRIPT"
mkdir -p /var/backups/agentswarm
chmod 700 /var/backups/agentswarm

cat >"$CRON_FILE" <<EOF
# AgentSwarm platform SQLite backup (P5.0)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
0 3 * * * root AGENTSWARM_DB=/var/lib/agentswarm/agentswarm.db AGENTSWARM_BACKUP_DIR=/var/backups/agentswarm ${BACKUP_SCRIPT} >> /var/log/agentswarm-backup.log 2>&1
EOF
chmod 644 "$CRON_FILE"

# Run once now so operators know backup works before relying on cron.
"$BACKUP_SCRIPT"
echo "Installed $CRON_FILE and ran initial backup."
