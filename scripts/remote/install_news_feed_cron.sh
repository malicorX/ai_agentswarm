#!/usr/bin/env bash
# Install periodic news feed enqueue on theebie.de (P5.2).
set -euo pipefail

ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
CRON_FILE="/etc/cron.d/agentswarm-news-feed"
SCRIPT="${ROOT}/scripts/enqueue_news_feed.py"
ENV_FILE="${AGENTSWARM_SWARM_ENV_FILE:-/etc/agentswarm/swarm.env}"

if [[ ! -f "$SCRIPT" ]]; then
  echo "Missing $SCRIPT" >&2
  exit 1
fi

cat >"$CRON_FILE" <<EOF
# AgentSwarm news feed ingestion (P5.2)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
0 */6 * * * root set -a && . ${ENV_FILE} && set +a && cd ${ROOT} && ${ROOT}/.venv/bin/python3 ${SCRIPT} >> /var/log/agentswarm-news-feed.log 2>&1
EOF
chmod 644 "$CRON_FILE"
echo "Installed $CRON_FILE (every 6 hours)"
