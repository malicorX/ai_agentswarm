from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.hardware_gates import (
    agent_meets_reviewer_hardware,
    public_parameters,
    required_reviewer_vram_gb,
    validate_presence_hardware,
)
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_public_parameters_default_off() -> None:
    params = public_parameters()
    assert params["enforced"] is False
    assert params["reviewer_min_vram_gb"] == 6.0


def test_validate_presence_requires_vram_for_reviewers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_HARDWARE_GATES_ENFORCE", "1")
    with pytest.raises(ValueError, match="vram_gb"):
        validate_presence_hardware(
            ["reviewer"],
            model_id="llm-mock-v1",
            vram_gb=None,
        )


def test_validate_presence_rejects_low_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_HARDWARE_GATES_ENFORCE", "1")
    with pytest.raises(ValueError, match="below required minimum"):
        validate_presence_hardware(
            ["reviewer"],
            model_id="llm-mock-v1",
            vram_gb=4.0,
        )


def test_agent_meets_reviewer_hardware_with_sufficient_vram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_HARDWARE_GATES_ENFORCE", "1")
    assert agent_meets_reviewer_hardware(model_id="llm-mock-v1", vram_gb=8.0) is True
    assert required_reviewer_vram_gb("llm-mock-v1") == 6.0


def test_presence_rejects_reviewer_without_vram_when_enforced(
    dispatch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENTSWARM_HARDWARE_GATES_ENFORCE", "1")
    agent_id, _ = register_agent(dispatch_client, ["reviewer"], owner="vram-guard")
    response = dispatch_client.post(
        f"/agents/{agent_id}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "ttl_sec": 60,
        },
    )
    assert response.status_code == 400
    assert "vram_gb" in response.json()["detail"].lower()


def test_dispatcher_skips_low_vram_reviewer(
    dispatch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENTSWARM_HARDWARE_GATES_ENFORCE", "1")
    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    weak_id, _ = register_agent(dispatch_client, ["reviewer"], owner="weak-reviewer")
    strong_id, _ = register_agent(dispatch_client, ["reviewer"], owner="strong-reviewer")
    dispatch_client.post(
        f"/agents/{weak_id}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "vram_gb": 4.0,
            "ttl_sec": 120,
        },
    )
    dispatch_client.post(
        f"/agents/{strong_id}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "vram_gb": 8.0,
            "ttl_sec": 120,
        },
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
    assert body["assignment"] is not None

    strong_pending = dispatch_client.get(
        f"/agents/{strong_id}/assignments/pending"
    ).json()
    weak_pending = dispatch_client.get(f"/agents/{weak_id}/assignments/pending").json()
    assert strong_pending is not None
    assert weak_pending is None


def test_platform_config_exposes_hardware(dispatch_client: TestClient) -> None:
    response = dispatch_client.get("/platform/config")
    assert response.status_code == 200
    hardware = response.json().get("hardware")
    assert isinstance(hardware, dict)
    assert hardware["reviewer_min_vram_gb"] == 6.0
