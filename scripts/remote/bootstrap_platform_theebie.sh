#!/usr/bin/env bash
# One-time theebie.de staging bootstrap: env secrets + Caddy path prefix.
set -euo pipefail

ROOT="${AGENTSWARM_INSTALL_ROOT:-/opt/agentswarm}"
ENV_FILE="${AGENTSWARM_PLATFORM_ENV_FILE:-/etc/agentswarm/platform.env}"
CADDY_FILE="${AGENTSWARM_CADDY_FILE:-/etc/caddy/Caddyfile}"
MARKER="# agentswarm platform api (p6.10)"

if [[ ! -f "$ROOT/docs/infra/theebie/agentswarm-platform.env.example" ]]; then
  echo "Missing $ROOT/docs/infra/theebie/agentswarm-platform.env.example â€” sync code first." >&2
  exit 1
fi

mkdir -p /etc/agentswarm
if [[ ! -f "$ENV_FILE" ]]; then
  ASSIGN_SECRET="$(openssl rand -hex 32)"
  SESSION_SECRET="$(openssl rand -hex 32)"
  BOOTSTRAP_TOKEN="$(openssl rand -hex 16)"
  sed \
    -e "s/change-me-long-random-dispatch-hmac-secret/$ASSIGN_SECRET/" \
    -e "s/change-me-long-random-session-secret/$SESSION_SECRET/" \
    -e "s/change-me-maintainer-bootstrap/$BOOTSTRAP_TOKEN/" \
    "$ROOT/docs/infra/theebie/agentswarm-platform.env.example" >"$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE with generated secrets."
else
  echo "Env file exists: $ENV_FILE"
fi

if ! grep -qF "$MARKER" "$CADDY_FILE"; then
  cp "$CADDY_FILE" "${CADDY_FILE}.bak.$(date +%s)"
  awk -v marker="$MARKER" '
    /handle_path \/sites\* \{/ && !done {
      print ""
      print "  " marker
      print "  handle_path /agentswarm/api/* {"
      print "    uri strip_prefix /agentswarm/api"
      print "    reverse_proxy 127.0.0.1:8010"
      print "  }"
      print ""
      done=1
    }
    { print }
  ' "$CADDY_FILE" >"${CADDY_FILE}.tmp"
  mv "${CADDY_FILE}.tmp" "$CADDY_FILE"
  caddy validate --config "$CADDY_FILE"
  systemctl reload caddy
  echo "Inserted Caddy handle_path for /agentswarm/api"
else
  echo "Caddy already configured for AgentSwarm API."
fi
