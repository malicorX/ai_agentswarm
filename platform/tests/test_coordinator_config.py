from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_platform_config_exposes_coordinator_block(dispatch_client: TestClient) -> None:
    response = dispatch_client.get("/platform/config")
    assert response.status_code == 200
    coordinator = response.json().get("coordinator")
    assert isinstance(coordinator, dict)
    assert coordinator["default_plan"] == "deterministic"
    assert coordinator["llm_planner"] == "optional_single_shot"
    assert "creative.text" in coordinator["allowed_immediate_task_types"]
    assert "reviewer.subjective" in coordinator["allowed_deferred_task_types"]
