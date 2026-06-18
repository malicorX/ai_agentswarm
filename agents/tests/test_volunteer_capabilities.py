from __future__ import annotations

from agentswarm_agents.volunteer_capabilities import (
    default_generalist_capabilities,
    parse_capabilities_field,
)


def test_parse_capabilities_all_keyword() -> None:
    assert parse_capabilities_field("all") == default_generalist_capabilities()
    assert parse_capabilities_field("") == default_generalist_capabilities()


def test_generalist_includes_coordinator_and_sandbox() -> None:
    caps = default_generalist_capabilities()
    assert "coordinator" in caps
    assert "codewriter" in caps
    assert "sandbox.test" in caps
    assert "reviewer" in caps
