from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from test_creative_subjective import RUBRIC, _pending, _presence, _submit_assignment
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def _reject_goal_flow(dispatch_client: TestClient) -> tuple[str, str]:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-appeal")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-appeal"
    )
    creative_id, creative_priv = register_agent(
        dispatch_client, ["creative"], owner="creative-appeal"
    )
    reviewer_id, reviewer_priv = register_agent(
        dispatch_client, ["reviewer"], owner="reviewer-appeal"
    )

    _presence(dispatch_client, coordinator_id, ["coordinator"])
    _presence(dispatch_client, creative_id, ["creative"])
    _presence(dispatch_client, reviewer_id, ["reviewer"])

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Appeal this poem",
            "rubric": RUBRIC,
            "min_reviewers": 1,
            "pass_threshold": 8.0,
        },
    )
    assert goal_resp.status_code == 200
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = _pending(dispatch_client, coordinator_id)
    assert coord_assignment is not None
    _submit_assignment(
        dispatch_client, coordinator_id, coord_priv, coord_assignment, {"goal_id": goal_id}
    )

    creative_assignment = _pending(dispatch_client, creative_id)
    assert creative_assignment is not None
    _submit_assignment(
        dispatch_client,
        creative_id,
        creative_priv,
        creative_assignment,
        {"text": "Draft text."},
    )

    reviewer_assignment = _pending(dispatch_client, reviewer_id)
    assert reviewer_assignment is not None
    _submit_assignment(
        dispatch_client,
        reviewer_id,
        reviewer_priv,
        reviewer_assignment,
        {"scores": {"quality": 3.0}, "rationale": "Too weak."},
    )

    goal = dispatch_client.get(f"/creative/goals/{goal_id}")
    assert goal.json()["status"] == "rejected"
    return goal_id, poster_id


def test_file_appeal_on_rejected_goal(dispatch_client: TestClient) -> None:
    goal_id, poster_id = _reject_goal_flow(dispatch_client)
    appeal = dispatch_client.post(
        f"/creative/goals/{goal_id}/appeal",
        json={
            "filed_by_agent_id": poster_id,
            "message": "The jury misread the rubric; please review again.",
        },
    )
    assert appeal.status_code == 200
    body = appeal.json()
    assert body["status"] == "pending"
    goal = dispatch_client.get(f"/creative/goals/{goal_id}")
    assert goal.json()["appeal"]["status"] == "pending"


def test_appeal_rejected_for_non_poster(dispatch_client: TestClient) -> None:
    goal_id, poster_id = _reject_goal_flow(dispatch_client)
    other_id, _ = register_agent(dispatch_client, ["codewriter"], owner="other-appeal")
    assert other_id != poster_id
    appeal = dispatch_client.post(
        f"/creative/goals/{goal_id}/appeal",
        json={
            "filed_by_agent_id": other_id,
            "message": "I should not be allowed to file this appeal.",
        },
    )
    assert appeal.status_code == 400


def test_overturn_appeal_verifies_goal_and_refunds_poster(dispatch_client: TestClient) -> None:
    goal_id, poster_id = _reject_goal_flow(dispatch_client)
    credits_before = dispatch_client.get(f"/agents/{poster_id}/credits").json()["balance"]
    dispatch_client.post(
        f"/creative/goals/{goal_id}/appeal",
        json={
            "filed_by_agent_id": poster_id,
            "message": "Human moderator please overturn this subjective reject.",
        },
    )
    resolved = dispatch_client.post(
        f"/creative/goals/{goal_id}/appeal/resolve",
        json={"decision": "overturn", "resolution_note": "Rubric misapplied."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "overturned"
    goal = dispatch_client.get(f"/creative/goals/{goal_id}")
    assert goal.json()["status"] == "verified"
    credits_after = dispatch_client.get(f"/agents/{poster_id}/credits").json()["balance"]
    assert credits_after == credits_before + 50.0


def test_uphold_appeal_keeps_rejected(dispatch_client: TestClient) -> None:
    goal_id, poster_id = _reject_goal_flow(dispatch_client)
    dispatch_client.post(
        f"/creative/goals/{goal_id}/appeal",
        json={
            "filed_by_agent_id": poster_id,
            "message": "Please reconsider this rejected creative goal outcome.",
        },
    )
    resolved = dispatch_client.post(
        f"/creative/goals/{goal_id}/appeal/resolve",
        json={"decision": "uphold", "resolution_note": "Scores stand."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "upheld"
    goal = dispatch_client.get(f"/creative/goals/{goal_id}")
    assert goal.json()["status"] == "rejected"
