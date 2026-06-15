#!/usr/bin/env bash
# Verify MCP adapter tool registration (P5.5).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AGENTSWARM_PLATFORM_URL="${AGENTSWARM_PLATFORM_URL:-${AGENTSWARM_STAGING_API_URL:-https://theebie.de/agentswarm/api}}"
python scripts/verify_mcp_adapter.py
