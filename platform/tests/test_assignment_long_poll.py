from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_LONG_POLL_MAX_SEC", "5")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_LONG_POLL_INTERVAL_SEC", "0.05")
    return client


def test_platform_config_exposes_dispatch_long_poll(dispatch_client: TestClient) -> None:
    response = dispatch_client.get("/platform/config")
    assert response.status_code == 200
    dispatch = response.json().get("dispatch")
    assert isinstance(dispatch, dict)
    assert dispatch["long_poll_max_sec"] == 5.0


def test_pending_returns_immediately_when_assigned(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-immediate")
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-immediate")
    dispatch_client.post(
        f"/agents/{reviewer_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 60},
    )
    dispatch_client.post(
        f"/agents/{poster_id}/presence",
        json={"status": "idle", "capabilities": ["codewriter"], "ttl_sec": 60},
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
            "constraints": {"exclude_owners": ["poster-immediate"]},
        },
    )
    assert need.status_code == 200

    started = time.monotonic()
    pending = dispatch_client.get(
        f"/agents/{reviewer_id}/assignments/pending",
        params={"wait_sec": 2},
    )
    elapsed = time.monotonic() - started
    assert pending.status_code == 200
    assert pending.json() is not None
    assert elapsed < 1.5


def test_wait_endpoint_times_out_empty(dispatch_client: TestClient) -> None:
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-wait")
    dispatch_client.post(
        f"/agents/{reviewer_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 60},
    )
    started = time.monotonic()
    response = dispatch_client.get(
        f"/agents/{reviewer_id}/assignments/wait",
        params={"wait_sec": 0.2},
    )
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert response.json() is None
    assert elapsed >= 0.15


def test_wait_sec_above_max_returns_400(dispatch_client: TestClient) -> None:
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-max")
    response = dispatch_client.get(
        f"/agents/{reviewer_id}/assignments/pending",
        params={"wait_sec": 99},
    )
    assert response.status_code == 400
    assert "maximum" in response.json()["detail"].lower()


def test_assignment_arrives_during_long_poll(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-delay")
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-delay")
    dispatch_client.post(
        f"/agents/{reviewer_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 60},
    )
    dispatch_client.post(
        f"/agents/{poster_id}/presence",
        json={"status": "idle", "capabilities": ["codewriter"], "ttl_sec": 60},
    )

    def assign_later() -> None:
        time.sleep(0.15)
        dispatch_client.post(
            "/pool/need",
            json={
                "role": "reviewer",
                "capability_required": "reviewer",
                "task_type": "reviewer.subjective",
                "payload": {
                    "capsule": {
                        "brief": "Score delayed poem",
                        "rubric": [{"id": "quality", "weight": 1.0}],
                    }
                },
                "constraints": {"exclude_owners": ["poster-delay"]},
            },
        )

    thread = threading.Thread(target=assign_later)
    thread.start()
    response = dispatch_client.get(
        f"/agents/{reviewer_id}/assignments/wait",
        params={"wait_sec": 2},
    )
    thread.join(timeout=3)
    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["task_id"]
