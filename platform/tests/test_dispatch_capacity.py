from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def _presence(
    client: TestClient,
    agent_id: str,
    *,
    capabilities: list[str],
    status: str = "idle",
) -> None:
    response = client.post(
        f"/agents/{agent_id}/presence",
        json={
            "status": status,
            "capabilities": capabilities,
            "model_id": "llm-test",
            "ttl_sec": 120,
        },
    )
    assert response.status_code == 200


def test_dispatch_capacity_empty(dispatch_client: TestClient) -> None:
    response = dispatch_client.get("/dispatch/capacity")
    assert response.status_code == 200
    body = response.json()
    assert body["assignment_mode"] == "dispatch"
    assert body["capabilities"] == {}
    assert body["totals"] == {
        "idle_agents": 0,
        "busy_agents": 0,
        "tracked_agents": 0,
    }


def test_dispatch_capacity_counts_idle_and_busy(dispatch_client: TestClient) -> None:
    coordinator_id, _ = register_agent(
        dispatch_client, ["coordinator"], owner="coord-capacity"
    )
    coder_id, _ = register_agent(dispatch_client, ["codewriter"], owner="coder-capacity")
    reviewer_id, _ = register_agent(
        dispatch_client, ["reviewer"], owner="reviewer-capacity"
    )

    _presence(dispatch_client, coordinator_id, capabilities=["coordinator"], status="idle")
    _presence(dispatch_client, coder_id, capabilities=["codewriter"], status="busy")
    _presence(dispatch_client, reviewer_id, capabilities=["reviewer"], status="idle")

    response = dispatch_client.get("/dispatch/capacity")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["idle_agents"] == 2
    assert body["totals"]["busy_agents"] == 1
    assert body["totals"]["tracked_agents"] == 3
    assert body["capabilities"]["coordinator"]["idle"] == 1
    assert body["capabilities"]["codewriter"]["busy"] == 1
    assert body["capabilities"]["reviewer"]["idle"] == 1
    assert len(body["capabilities"]["codewriter"]["agents"]) == 1
    assert body["capabilities"]["codewriter"]["agents"][0]["owner"] == "coder-capacity"


def test_dispatch_capacity_requires_auth_when_enforced(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    denied = auth_client.get("/dispatch/capacity")
    assert denied.status_code == 401
    allowed = auth_client.get(
        "/dispatch/capacity",
        headers={"X-Bootstrap-Token": "test-bootstrap"},
    )
    assert allowed.status_code == 200
