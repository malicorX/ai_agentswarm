#!/usr/bin/env python3
"""Verify the AgentSwarm MCP adapter package (P5.5)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "packages" / "mcp-adapter" / "src"))

from agentswarm_mcp import PROTOCOL_TOOL_NAMES
from agentswarm_mcp.server import list_tool_names


def verify_mcp_adapter(*, platform_url: str | None = None) -> dict[str, str]:
    tools = set(list_tool_names())
    expected = set(PROTOCOL_TOOL_NAMES)
    if tools != expected:
        missing = expected - tools
        extra = tools - expected
        raise RuntimeError(f"tool mismatch missing={missing!r} extra={extra!r}")

    result = {"tools": str(len(tools)), "tool_names": "ok"}

    url = (
        platform_url
        or os.environ.get("AGENTSWARM_PLATFORM_URL")
        or os.environ.get("AGENTSWARM_STAGING_API_URL")
    )
    if url:
        clean = url.strip().rstrip("/")
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            health = client.get(f"{clean}/health")
            health.raise_for_status()
            if health.json() != {"status": "ok"}:
                raise RuntimeError(f"unexpected health: {health.json()!r}")
        result["platform_health"] = "ok"
        result["platform_url"] = clean

    return result


def main() -> int:
    try:
        outcome = verify_mcp_adapter()
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"MCP adapter verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"MCP adapter OK ({outcome})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
