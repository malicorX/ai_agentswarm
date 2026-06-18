from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from test_coordinator_decompose import _presence
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_realign_goal_dispatch_reclaims_outside_team(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-realign")
    ghost_coord_id, _ = register_agent(
        dispatch_client, ["coordinator"], owner="ghost-coordinator"
    )
    _presence(dispatch_client, ghost_coord_id, ["coordinator"])

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Print primes",
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200
    goal_id = goal_resp.json()["goal_id"]

    ghost_assignment = dispatch_client.get(
        f"/agents/{ghost_coord_id}/assignments/pending"
    ).json()
    assert ghost_assignment is not None

    team_coord_id, _ = register_agent(
        dispatch_client, ["coordinator"], owner="team-coordinator"
    )
    _presence(dispatch_client, team_coord_id, ["coordinator"])

    realign = dispatch_client.post(
        f"/creative/goals/{goal_id}/realign-dispatch",
        json={"include_owners": ["team-coordinator"]},
    )
    assert realign.status_code == 200, realign.text
    body = realign.json()
    assert body["goal_id"] == goal_id
    assert body["reclaimed_need_ids"]

    team_assignment = dispatch_client.get(
        f"/agents/{team_coord_id}/assignments/pending"
    ).json()
    assert team_assignment is not None
    assert team_assignment["task_type"] == "coordinator.decompose"

    ghost_after = dispatch_client.get(
        f"/agents/{ghost_coord_id}/assignments/pending"
    ).json()
    assert ghost_after is None
