from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64


@pytest.fixture
def dispatch_auth_client(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return auth_client


def _register_poster(client: TestClient) -> str:
    pub_raw, _priv_raw = generate_keypair()
    response = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub_raw),
            "owner": "poster-replay",
            "capabilities": ["codewriter"],
        },
        headers={"X-Bootstrap-Token": "test-bootstrap"},
    )
    assert response.status_code == 200
    return response.json()["agent_id"]


def test_replay_context_requires_owner(dispatch_auth_client: TestClient) -> None:
    poster_id = _register_poster(dispatch_auth_client)
    create = dispatch_auth_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "replay probe",
            "rubric": [{"id": "quality", "weight": 1.0}],
            "goal_kind": "engineering",
            "verification_spec": {"workspace_mode": "git", "fixture": "primes"},
            "workspace": {
                "mode": "git",
                "repo_url": "root@host:/repo.git",
                "default_branch": "main",
            },
        },
        headers={"X-Bootstrap-Token": "test-bootstrap"},
    )
    assert create.status_code == 200
    goal_id = create.json()["goal_id"]

    denied = dispatch_auth_client.get(f"/creative/goals/{goal_id}/replay-context")
    assert denied.status_code == 401

    ok = dispatch_auth_client.get(
        f"/creative/goals/{goal_id}/replay-context",
        headers={"X-Bootstrap-Token": "test-bootstrap"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["goal_id"] == goal_id
    assert body["workspace"]["repo_url"] == "root@host:/repo.git"
