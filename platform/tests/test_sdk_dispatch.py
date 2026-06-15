from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64
from agentswarm_sdk import (
    AgentClient,
    DispatchClient,
    PlatformClient,
    assert_dispatch_mode,
    fetch_platform_config,
    platform_assignment_mode,
    verify_assignment_signature,
)
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-sdk-dispatch-secret")
    return client


class _SdkHttpShim:
    """Route SDK httpx calls through FastAPI TestClient."""

    base_url = "http://testserver"

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def _path(self, url: str) -> str:
        if url.startswith("/"):
            return url
        return url.replace(self.base_url, "") or "/"

    def get(self, url: str, *, params=None, timeout=None):
        return self._client.get(self._path(url), params=params)

    def post(self, url: str, *, json=None, headers=None, timeout=None):
        return self._client.post(self._path(url), json=json, headers=headers)


@pytest.fixture
def sdk_http(dispatch_client: TestClient) -> _SdkHttpShim:
    return _SdkHttpShim(dispatch_client)


def test_platform_assignment_mode_prefers_assignment_block() -> None:
    config = {
        "assignment_mode": "pull",
        "assignment": {"mode": "dispatch"},
    }
    assert platform_assignment_mode(config) == "dispatch"


def test_assert_dispatch_mode_rejects_pull(
    sdk_http: _SdkHttpShim, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "pull")

    def fetch(url: str) -> dict:
        response = sdk_http.get("/platform/config")
        response.raise_for_status()
        return response.json()

    monkeypatch.setattr(
        "agentswarm_sdk.dispatch_client.fetch_platform_config",
        lambda _base_url: fetch(""),
    )
    with pytest.raises(RuntimeError, match="dispatch"):
        assert_dispatch_mode("http://testserver")


def test_fetch_platform_config(
    sdk_http: _SdkHttpShim, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agentswarm_sdk.dispatch_client.httpx.get",
        lambda url, timeout=30.0: sdk_http.get("/platform/config"),
    )
    config = fetch_platform_config("http://testserver")
    assert platform_assignment_mode(config) == "dispatch"


def _register_dispatch_sdk(
    sdk_http: _SdkHttpShim,
    capabilities: list[str],
    owner: str,
) -> DispatchClient:
    pub, priv = generate_keypair()
    registered = AgentClient.register(
        "http://testserver",
        owner,
        capabilities,
        priv,
        pub,
        http=sdk_http,
    )
    return DispatchClient(
        registered.base_url,
        registered.agent_id,
        priv,
        http=sdk_http,
    )


def test_sdk_dispatch_heartbeat_and_assignment(
    dispatch_client: TestClient,
    sdk_http: _SdkHttpShim,
) -> None:
    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    client = _register_dispatch_sdk(sdk_http, ["reviewer"], "reviewer-owner")

    client.heartbeat(["reviewer"], status="idle", ttl_sec=120)

    platform = PlatformClient("http://testserver", http=sdk_http)
    need = platform.create_pool_need(
        role="reviewer",
        capability_required="reviewer",
        task_type="reviewer.subjective",
        payload={
            "capsule": {
                "brief": "Score this poem",
                "rubric": [{"id": "quality", "weight": 1.0}],
            }
        },
        constraints={"exclude_owners": ["poster-owner"]},
    )
    assert need["assigned"] is True

    assignment = client.get_pending_assignment()
    assert assignment is not None
    assert assignment["task_id"] == need["task_id"]
    verify_assignment_signature(assignment, client.agent_id)


def test_sdk_dispatch_submit_includes_platform_detail(
    dispatch_client: TestClient,
    sdk_http: _SdkHttpShim,
) -> None:
    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    client = _register_dispatch_sdk(sdk_http, ["reviewer"], "reviewer-owner")
    client.heartbeat(["reviewer"], status="idle", ttl_sec=120)

    platform = PlatformClient("http://testserver", http=sdk_http)
    platform.create_pool_need(
        role="reviewer",
        capability_required="reviewer",
        task_type="reviewer.subjective",
        payload={
            "capsule": {
                "brief": "Score",
                "rubric": [{"id": "quality", "weight": 1.0}],
            }
        },
        constraints={"exclude_owners": ["poster-owner"]},
    )
    assignment = client.get_pending_assignment()
    assert assignment is not None

    bad_assignment = {**assignment, "claim_token": "not-a-valid-claim-token"}
    with pytest.raises(RuntimeError, match="invalid claim token"):
        client.submit_assignment(
            bad_assignment,
            {"scores": {"quality": 7.0}, "rationale": "bad token"},
        )


def test_sdk_dispatch_submit_reviewer_goal_flow(
    dispatch_client: TestClient,
    sdk_http: _SdkHttpShim,
) -> None:
    from test_creative_subjective import RUBRIC, _pending, _presence, _submit_assignment

    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-sdk-submit")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-sdk-submit"
    )
    creative_id, creative_priv = register_agent(
        dispatch_client, ["creative"], owner="creative-sdk-submit"
    )
    reviewer_client = _register_dispatch_sdk(sdk_http, ["reviewer"], "reviewer-sdk-submit")

    _presence(dispatch_client, coordinator_id, ["coordinator"])
    _presence(dispatch_client, creative_id, ["creative"])
    reviewer_client.heartbeat(["reviewer"], status="idle", ttl_sec=120)

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "SDK dispatch submit test",
            "rubric": RUBRIC,
            "min_reviewers": 1,
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
        {"text": "Dispatch SDK routes the poem home."},
    )

    assignment = reviewer_client.get_pending_assignment()
    assert assignment is not None
    verify_assignment_signature(assignment, reviewer_client.agent_id)
    submission_id = reviewer_client.submit_assignment(
        assignment,
        {
            "scores": {"quality": 8.0},
            "rationale": "Clear and on-brief.",
        },
    )
    assert submission_id

    goal = dispatch_client.get(f"/creative/goals/{goal_id}")
    assert goal.json()["status"] == "verified"
