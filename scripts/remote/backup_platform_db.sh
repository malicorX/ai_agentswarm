#!/usr/bin/env bash
# Daily SQLite backup for AgentSwarm platform (installed by install_platform_backup_cron.sh).
set -euo pipefail

DB="${AGENTSWARM_DB:-/var/lib/agentswarm/agentswarm.db}"
BACKUP_DIR="${AGENTSWARM_BACKUP_DIR:-/var/backups/agentswarm}"
RETENTION_DAYS="${AGENTSWARM_BACKUP_RETENTION_DAYS:-14}"

if [[ ! -f "$DB" ]]; then
  echo "Database not found: $DB" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d)"
DEST="${BACKUP_DIR}/agentswarm-${STAMP}.db"

python3 - "$DB" "$DEST" "$BACKUP_DIR" "$RETENTION_DAYS" <<'PY'
import sqlite3
import sys
from pathlib import Path

src, dest, backup_dir, retention = sys.argv[1:5]
with sqlite3.connect(src) as source:
    with sqlite3.connect(dest) as target:
        source.backup(target)
Path(dest).chmod(0o600)
root = Path(backup_dir)
for path in sorted(root.glob("agentswarm-*.db")):
    age_days = (__import__("time").time() - path.stat().st_mtime) / 86400
    if age_days > float(retention):
        path.unlink()
print(f"Backup written: {dest}")
PY
