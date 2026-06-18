from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from test_task_flow import register_agent


def _post_engineering_goal(client: TestClient, poster_id: str, *, brief: str) -> str:
    response = client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": brief,
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
            "min_reviewers": 1,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["goal_id"]


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_list_creative_goals_requires_auth(auth_client: TestClient) -> None:
    response = auth_client.get("/creative/goals")
    assert response.status_code == 401


def test_list_creative_goals_search_and_filter(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-list")
    goal_a = _post_engineering_goal(
        dispatch_client,
        poster_id,
        brief="Print first 100 primes for listing test",
    )
    goal_b = _post_engineering_goal(
        dispatch_client,
        poster_id,
        brief="Another unrelated brief",
    )

    listed = dispatch_client.get("/creative/goals", params={"limit": 10})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 2
    ids = {item["goal_id"] for item in body["goals"]}
    assert goal_a in ids
    assert goal_b in ids

    search = dispatch_client.get("/creative/goals", params={"q": "listing test"})
    assert search.status_code == 200
    search_ids = {item["goal_id"] for item in search.json()["goals"]}
    assert goal_a in search_ids
    assert goal_b not in search_ids

    pending = dispatch_client.get("/creative/goals", params={"status": "pending"})
    assert pending.status_code == 200
    assert all(item["status"] == "pending" for item in pending.json()["goals"])
