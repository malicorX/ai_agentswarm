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


def test_resume_goal_dispatch_reclaims_like_realign(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-resume")
    ghost_coord_id, _ = register_agent(
        dispatch_client, ["coordinator"], owner="ghost-coordinator-resume"
    )
    _presence(dispatch_client, ghost_coord_id, ["coordinator"])

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Resume reclaim test",
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
        dispatch_client, ["coordinator"], owner="team-coordinator-resume"
    )
    _presence(dispatch_client, team_coord_id, ["coordinator"])

    resume = dispatch_client.post(
        f"/creative/goals/{goal_id}/resume-dispatch",
        json={"include_owners": ["team-coordinator-resume"]},
    )
    assert resume.status_code == 200, resume.text
    body = resume.json()
    assert body["goal_id"] == goal_id
    assert body["reclaimed_need_ids"]
    assert body["healed_task_ids"] == []

    team_assignment = dispatch_client.get(
        f"/agents/{team_coord_id}/assignments/pending"
    ).json()
    assert team_assignment is not None
    assert team_assignment["task_type"] == "coordinator.decompose"


def test_resume_goal_dispatch_rejects_terminal(dispatch_client: TestClient) -> None:
    import agentswarm_platform.main as main_module

    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-terminal")
    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Terminal resume test",
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200
    goal_id = goal_resp.json()["goal_id"]

    with main_module.store._conn() as conn:
        conn.execute(
            "UPDATE creative_goals SET status = ? WHERE goal_id = ?",
            ("verified", goal_id),
        )

    resume = dispatch_client.post(
        f"/creative/goals/{goal_id}/resume-dispatch",
        json={"include_owners": ["volunteer"]},
    )
    assert resume.status_code == 400
    assert "terminal" in resume.json()["detail"]
