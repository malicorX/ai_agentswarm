from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.coordinator_plan import build_default_creative_goal_plan
from agentswarm_platform.crypto import sign_payload
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def _presence(client: TestClient, agent_id: str, capabilities: list[str]) -> None:
    response = client.post(
        f"/agents/{agent_id}/presence",
        json={"status": "idle", "capabilities": capabilities, "ttl_sec": 120},
    )
    assert response.status_code == 200


def _submit(client: TestClient, agent_id: str, private_key: bytes, assignment: dict, result: dict) -> None:
    signature = sign_payload(private_key, {"task_id": assignment["task_id"], "result": result})
    response = client.post(
        "/tasks/submit",
        json={
            "claim_token": assignment["claim_token"],
            "result": result,
            "signature": signature,
        },
    )
    assert response.status_code == 200, response.text


RUBRIC = [{"id": "quality", "weight": 1.0}]


def test_coordinator_plan_emits_pool_needs(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-plan")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-plan"
    )
    creative_id, _ = register_agent(dispatch_client, ["creative"], owner="creative-plan")
    _presence(dispatch_client, coordinator_id, ["coordinator"])
    _presence(dispatch_client, creative_id, ["creative"])

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Write a haiku",
            "rubric": RUBRIC,
            "min_reviewers": 2,
        },
    )
    goal_id = goal_resp.json()["goal_id"]
    plan = build_default_creative_goal_plan(
        {
            "goal_id": goal_id,
            "brief": "Write a haiku",
            "rubric": RUBRIC,
            "min_reviewers": 2,
        }
    )

    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    assert coord_assignment is not None
    _submit(dispatch_client, coordinator_id, coord_priv, coord_assignment, plan)

    goal = dispatch_client.get(f"/creative/goals/{goal_id}").json()
    assert len(goal["deferred_pool_needs"]) == 1
    assert goal["deferred_pool_needs"][0]["spec"]["count"] == 2

    creative_assignment = dispatch_client.get(
        f"/agents/{creative_id}/assignments/pending"
    ).json()
    assert creative_assignment is not None
    assert creative_assignment["task_type"] == "creative.text"


def test_coordinator_assignment_cleared_after_submit(dispatch_client: TestClient) -> None:
    from agentswarm_platform import main as platform_main

    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-lease")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-lease"
    )
    _presence(dispatch_client, coordinator_id, ["coordinator"])

    goal_id = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Write a haiku",
            "rubric": RUBRIC,
            "min_reviewers": 1,
        },
    ).json()["goal_id"]
    plan = build_default_creative_goal_plan(
        {
            "goal_id": goal_id,
            "brief": "Write a haiku",
            "rubric": RUBRIC,
            "min_reviewers": 1,
        }
    )

    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    assert coord_assignment is not None
    _submit(dispatch_client, coordinator_id, coord_priv, coord_assignment, plan)

    repeat = dispatch_client.get(f"/agents/{coordinator_id}/assignments/pending").json()
    assert repeat is None

    with platform_main.store._conn() as conn:
        need = conn.execute(
            """
            SELECT status FROM pool_needs
            WHERE task_id = ?
            """,
            (coord_assignment["task_id"],),
        ).fetchone()
    assert need is not None
    assert need["status"] == "fulfilled"


def test_coordinator_rejects_invalid_plan(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-bad-plan")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-bad-plan"
    )
    _presence(dispatch_client, coordinator_id, ["coordinator"])

    goal_id = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "bad",
            "rubric": RUBRIC,
            "min_reviewers": 1,
        },
    ).json()["goal_id"]

    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    signature = sign_payload(
        coord_priv,
        {
            "task_id": coord_assignment["task_id"],
            "result": {"goal_id": goal_id, "pool_needs": []},
        },
    )
    response = dispatch_client.post(
        "/tasks/submit",
        json={
            "claim_token": coord_assignment["claim_token"],
            "result": {"goal_id": goal_id, "pool_needs": []},
            "signature": signature,
        },
    )
    assert response.status_code == 400
    assert "pool_needs" in response.json()["detail"]
