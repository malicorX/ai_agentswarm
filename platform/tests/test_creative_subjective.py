from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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


def _submit_assignment(
    client: TestClient,
    agent_id: str,
    private_key: bytes,
    assignment: dict,
    result: dict,
) -> None:
    task_id = assignment["task_id"]
    signature = sign_payload(private_key, {"task_id": task_id, "result": result})
    response = client.post(
        "/tasks/submit",
        json={
            "claim_token": assignment["claim_token"],
            "result": result,
            "signature": signature,
        },
    )
    assert response.status_code == 200, response.text


def _pending(client: TestClient, agent_id: str) -> dict | None:
    response = client.get(f"/agents/{agent_id}/assignments/pending")
    assert response.status_code == 200
    return response.json()


RUBRIC = [{"id": "quality", "weight": 1.0, "description": "Overall craft"}]


def test_credits_initial_and_goal_burn(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-credits")
    credits = dispatch_client.get(f"/agents/{poster_id}/credits")
    assert credits.status_code == 200
    assert credits.json()["balance"] == 100.0
    assert credits.json()["enabled"] is True

    goal = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Write a haiku about dispatch",
            "rubric": RUBRIC,
            "min_reviewers": 1,
        },
    )
    assert goal.status_code == 200
    after = dispatch_client.get(f"/agents/{poster_id}/credits")
    assert after.json()["balance"] == 50.0


def test_insufficient_credits_rejected(
    dispatch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENTSWARM_CREDITS_INITIAL", "40")
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-poor")
    dispatch_client.get(f"/agents/{poster_id}/credits")
    goal = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Too expensive",
            "rubric": RUBRIC,
        },
    )
    assert goal.status_code == 400
    assert "insufficient credits" in goal.json()["detail"]


def test_goal_burn_scales_with_difficulty(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-difficulty")
    dispatch_client.get(f"/agents/{poster_id}/credits")
    goal = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Harder poem",
            "rubric": RUBRIC,
            "min_reviewers": 1,
            "difficulty": 2.0,
        },
    )
    assert goal.status_code == 200
    after = dispatch_client.get(f"/agents/{poster_id}/credits")
    assert after.json()["balance"] == 0.0


def test_platform_config_exposes_credit_pricing(dispatch_client: TestClient) -> None:
    response = dispatch_client.get("/platform/config")
    assert response.status_code == 200
    credits = response.json().get("credits")
    assert isinstance(credits, dict)
    assert credits["pricing"]["creative.goal"]["post_cost"] == 50.0
    models = response.json().get("models")
    assert isinstance(models, dict)
    assert models["version"] == "2"


def test_subjective_quorum_pass_and_reviewer_mint(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-owner"
    )
    creative_id, creative_priv = register_agent(
        dispatch_client, ["creative"], owner="creative-owner"
    )
    reviewer_ids: list[tuple[str, bytes]] = []
    for idx in range(3):
        reviewer_ids.append(
            register_agent(dispatch_client, ["reviewer"], owner=f"reviewer-owner-{idx}")
        )

    for agent_id, caps in (
        (coordinator_id, ["coordinator"]),
        (creative_id, ["creative"]),
        *((rid, ["reviewer"]) for rid, _ in reviewer_ids),
    ):
        _presence(dispatch_client, agent_id, caps)

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "A short poem about volunteer compute",
            "rubric": RUBRIC,
            "min_reviewers": 3,
            "pass_threshold": 6.0,
        },
    )
    assert goal_resp.status_code == 200
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = _pending(dispatch_client, coordinator_id)
    assert coord_assignment is not None
    _submit_assignment(
        dispatch_client,
        coordinator_id,
        coord_priv,
        coord_assignment,
        {"goal_id": goal_id, "acknowledged": True},
    )

    creative_assignment = _pending(dispatch_client, creative_id)
    assert creative_assignment is not None
    _submit_assignment(
        dispatch_client,
        creative_id,
        creative_priv,
        creative_assignment,
        {"text": "Volunteers hum at night,\nDispatch assigns the next role,\nCredits balance right."},
    )

    for reviewer_id, reviewer_priv in reviewer_ids:
        assignment = _pending(dispatch_client, reviewer_id)
        assert assignment is not None
        _submit_assignment(
            dispatch_client,
            reviewer_id,
            reviewer_priv,
            assignment,
            {
                "scores": {"quality": 8.0},
                "rationale": "Strong imagery and on-brief.",
            },
        )

    goal = dispatch_client.get(f"/creative/goals/{goal_id}")
    assert goal.status_code == 200
    body = goal.json()
    assert body["status"] == "verified"
    assert body["aggregate_score"] >= 6.0
    assert len(body["reviews"]) == 3

    for reviewer_id, _ in reviewer_ids:
        credits = dispatch_client.get(f"/agents/{reviewer_id}/credits")
        assert credits.json()["balance"] == 115.0


def test_subjective_quorum_reject(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-reject")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-reject"
    )
    creative_id, creative_priv = register_agent(
        dispatch_client, ["creative"], owner="creative-reject"
    )
    reviewer_id, reviewer_priv = register_agent(
        dispatch_client, ["reviewer"], owner="reviewer-reject"
    )

    _presence(dispatch_client, coordinator_id, ["coordinator"])
    _presence(dispatch_client, creative_id, ["creative"])
    _presence(dispatch_client, reviewer_id, ["reviewer"])

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Fail this poem",
            "rubric": RUBRIC,
            "min_reviewers": 1,
            "pass_threshold": 8.0,
        },
    )
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = _pending(dispatch_client, coordinator_id)
    assert coord_assignment is not None
    _submit_assignment(
        dispatch_client,
        coordinator_id,
        coord_priv,
        coord_assignment,
        {"goal_id": goal_id},
    )

    creative_assignment = _pending(dispatch_client, creative_id)
    assert creative_assignment is not None
    _submit_assignment(
        dispatch_client,
        creative_id,
        creative_priv,
        creative_assignment,
        {"text": "Weak draft."},
    )

    reviewer_assignment = _pending(dispatch_client, reviewer_id)
    assert reviewer_assignment is not None
    _submit_assignment(
        dispatch_client,
        reviewer_id,
        reviewer_priv,
        reviewer_assignment,
        {"scores": {"quality": 4.0}, "rationale": "Below bar."},
    )

    goal = dispatch_client.get(f"/creative/goals/{goal_id}")
    assert goal.json()["status"] == "rejected"
    assert goal.json()["aggregate_score"] == 4.0
