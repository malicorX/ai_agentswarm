from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.assignment_config import assignment_mode
from agentswarm_platform.assignment_signing import sign_assignment, verify_assignment
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_assignment_mode_defaults_to_pull(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_ASSIGNMENT_MODE", raising=False)
    assert assignment_mode() == "pull"


def test_assignment_signature_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    payload = {"lease_id": "lease-1", "agent_id": "agent-1", "task_id": "task-1", "expires_at": "2026-06-15T00:00:00+00:00"}
    signature = sign_assignment(payload)
    assert verify_assignment(payload, signature)


def test_presence_heartbeat(dispatch_client: TestClient) -> None:
    agent_id, _ = register_agent(dispatch_client, ["reviewer"], owner="presence-owner")
    response = dispatch_client.post(
        f"/agents/{agent_id}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-test",
            "load": 0.1,
            "ttl_sec": 120,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == agent_id
    assert body["status"] == "idle"


def test_assignment_only_task_not_in_poll(dispatch_client: TestClient) -> None:
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    create = dispatch_client.post(
        "/tasks",
        json={
            "task_type": "reviewer.subjective",
            "capability_required": "reviewer",
            "payload": {"capsule": {"brief": "review poem"}},
            "assignment_only": True,
        },
    )
    assert create.status_code == 200
    polled = dispatch_client.get("/tasks/poll", params={"agent_id": reviewer_id, "capability": "reviewer"})
    assert polled.json() == []


def test_assignment_only_rejects_manual_claim(dispatch_client: TestClient) -> None:
    register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    create = dispatch_client.post(
        "/tasks",
        json={
            "task_type": "reviewer.subjective",
            "capability_required": "reviewer",
            "payload": {"capsule": {"brief": "review poem"}},
            "assignment_only": True,
        },
    )
    task_id = create.json()["task_id"]
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-c")
    claim = dispatch_client.post(f"/tasks/{task_id}/claim", json={"agent_id": reviewer_id})
    assert claim.status_code == 400
    assert "assignment-only" in claim.json()["detail"]


def test_pool_need_assigns_disjoint_reviewer(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-owner")
    dispatch_client.post(
        f"/agents/{reviewer_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    dispatch_client.post(
        f"/agents/{poster_id}/presence",
        json={"status": "idle", "capabilities": ["codewriter"], "ttl_sec": 120},
    )
    need = dispatch_client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {
                "capsule": {
                    "brief": "Score this poem",
                    "rubric": [{"id": "quality", "weight": 1.0}],
                }
            },
            "constraints": {"exclude_owners": ["poster-owner"]},
        },
    )
    assert need.status_code == 200
    body = need.json()
    assert body["assigned"] is True
    assignment = body["assignment"]
    assert assignment is not None
    assert assignment["task_id"] == body["task_id"]
    pending = dispatch_client.get(f"/agents/{reviewer_id}/assignments/pending")
    assert pending.status_code == 200
    pending_body = pending.json()
    assert pending_body is not None
    assert pending_body["task_id"] == body["task_id"]
    assert pending_body["claim_token"]
    poster_pending = dispatch_client.get(f"/agents/{poster_id}/assignments/pending")
    assert poster_pending.json() is None


def test_pool_need_rejects_pull_mode(client: TestClient) -> None:
    response = client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {},
        },
    )
    assert response.status_code == 400
    assert "dispatch" in response.json()["detail"]
