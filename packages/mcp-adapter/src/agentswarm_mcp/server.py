from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from agentswarm_mcp import bridge

mcp = FastMCP(
    "AgentSwarm",
    instructions=(
        "Thin MCP adapter over the AgentSwarm REST API (ADR 0003). "
        "Set AGENTSWARM_PLATFORM_URL. For signed calls, pass private_key_b64 "
        "or set AGENTSWARM_PRIVATE_KEY_B64."
    ),
)


def _default_base_url(base_url: str | None) -> str | None:
    if base_url:
        return base_url
    env = os.environ.get("AGENTSWARM_PLATFORM_URL")
    return env or None


@mcp.tool(name="agentswarm_register")
def agentswarm_register(
    owner: str,
    capabilities: list[str],
    public_key_b64: str,
    base_url: str | None = None,
    project_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Register an agent (POST /agents/register). Requires owner JWT or bootstrap token in env."""
    return bridge.register_agent(
        owner=owner,
        capabilities=capabilities,
        public_key_b64=public_key_b64,
        base_url=_default_base_url(base_url),
        project_ids=project_ids,
    )


@mcp.tool(name="agentswarm_poll_tasks")
def agentswarm_poll_tasks(
    agent_id: str,
    capability: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Poll open tasks for an agent (GET /tasks/poll)."""
    return bridge.poll_tasks(
        agent_id=agent_id,
        capability=capability,
        base_url=_default_base_url(base_url),
    )


@mcp.tool(name="agentswarm_claim_task")
def agentswarm_claim_task(
    agent_id: str,
    task_id: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Claim a task and receive a claim_token (POST /tasks/{id}/claim)."""
    return bridge.claim_task(
        agent_id=agent_id,
        task_id=task_id,
        base_url=_default_base_url(base_url),
    )


@mcp.tool(name="agentswarm_checkpoint")
def agentswarm_checkpoint(
    claim_token: str,
    partial_state_json: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Save partial task state (POST /tasks/checkpoint). partial_state_json is a JSON object string."""
    return bridge.checkpoint_task(
        claim_token=claim_token,
        partial_state=partial_state_json,
        base_url=_default_base_url(base_url),
    )


@mcp.tool(name="agentswarm_submit")
def agentswarm_submit(
    claim_token: str,
    task_id: str,
    result_json: str,
    private_key_b64: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Submit a signed task result (POST /tasks/submit). result_json is a JSON object string."""
    return bridge.submit_task(
        claim_token=claim_token,
        task_id=task_id,
        result=result_json,
        private_key_b64=private_key_b64,
        base_url=_default_base_url(base_url),
    )


@mcp.tool(name="agentswarm_poll_verifications")
def agentswarm_poll_verifications(
    agent_id: str,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Poll verification work for a reviewer agent (GET /verifications/poll)."""
    return bridge.poll_verifications(
        agent_id=agent_id,
        base_url=_default_base_url(base_url),
    )


@mcp.tool(name="agentswarm_claim_verification")
def agentswarm_claim_verification(
    agent_id: str,
    verification_id: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Claim a verification item (POST /verifications/{id}/claim)."""
    return bridge.claim_verification(
        agent_id=agent_id,
        verification_id=verification_id,
        base_url=_default_base_url(base_url),
    )


@mcp.tool(name="agentswarm_verify")
def agentswarm_verify(
    claim_token: str,
    verdict: str,
    task_id: str,
    submission_id: str,
    notes: str = "",
    private_key_b64: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Sign and post a verification verdict (POST /verifications/verify). verdict: approve or reject."""
    return bridge.verify_submission(
        claim_token=claim_token,
        verdict=verdict,
        task_id=task_id,
        submission_id=submission_id,
        notes=notes,
        private_key_b64=private_key_b64,
        base_url=_default_base_url(base_url),
    )


@mcp.resource("agentswarm://platform/config")
def platform_config_resource() -> str:
    """Read-only platform health and assignment mode."""
    import httpx

    base = bridge.platform_url()
    health = httpx.get(f"{base}/health", timeout=15.0)
    health.raise_for_status()
    config = httpx.get(f"{base}/platform/config", timeout=15.0)
    config.raise_for_status()
    return json.dumps(
        {"health": health.json(), "config": config.json()},
        indent=2,
    )


def list_tool_names() -> list[str]:
    """Return registered MCP tool names (for verify scripts)."""
    if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "list_tools"):
        tools = mcp._tool_manager.list_tools()
        return sorted(tool.name for tool in tools)
    return sorted(bridge.PROTOCOL_TOOL_NAMES)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
