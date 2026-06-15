from __future__ import annotations

from agentswarm_mcp import PROTOCOL_TOOL_NAMES
from agentswarm_mcp.server import list_tool_names, mcp


def test_protocol_tool_names_cover_adr_mapping() -> None:
    expected = {
        "agentswarm_register",
        "agentswarm_poll_tasks",
        "agentswarm_claim_task",
        "agentswarm_checkpoint",
        "agentswarm_submit",
        "agentswarm_poll_verifications",
        "agentswarm_claim_verification",
        "agentswarm_verify",
    }
    assert set(PROTOCOL_TOOL_NAMES) == expected


def test_mcp_server_registers_protocol_tools() -> None:
    names = set(list_tool_names())
    assert names == set(PROTOCOL_TOOL_NAMES)


def test_mcp_server_has_instructions() -> None:
    assert mcp.instructions is not None
    assert "REST" in mcp.instructions
