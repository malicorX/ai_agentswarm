from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.model_allowlist import (
    allowed_model_ids,
    public_parameters,
    validate_model_id,
)
from test_task_flow import register_agent

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ALLOWLIST = (
    REPO_ROOT / "agents" / "src" / "agentswarm_agents" / "model_allowlist.json"
)
PLATFORM_ALLOWLIST = (
    REPO_ROOT / "platform" / "src" / "agentswarm_platform" / "data" / "model_allowlist.json"
)


def test_client_and_platform_allowlists_match() -> None:
    agents = json.loads(AGENTS_ALLOWLIST.read_text(encoding="utf-8"))
    platform = json.loads(PLATFORM_ALLOWLIST.read_text(encoding="utf-8"))
    assert agents == platform


def test_public_parameters_include_allowlist() -> None:
    params = public_parameters()
    assert params["version"] == "3"
    assert params["enforced"] is False
    assert any(item["id"] == "llm-mock-v1" for item in params["allowlist"])


def test_validate_model_id_when_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_MODEL_ALLOWLIST_ENFORCE", "1")
    validate_model_id("llm-mock-v1")
    with pytest.raises(ValueError, match="allowlist"):
        validate_model_id("unknown-model")


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_platform_config_exposes_models_allowlist(dispatch_client: TestClient) -> None:
    response = dispatch_client.get("/platform/config")
    assert response.status_code == 200
    models = response.json().get("models")
    assert isinstance(models, dict)
    assert models["version"] == "3"
    assert "llm-mock-v1" in allowed_model_ids()


def test_presence_rejects_unknown_model_when_enforced(
    dispatch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENTSWARM_MODEL_ALLOWLIST_ENFORCE", "1")
    agent_id, _ = register_agent(dispatch_client, ["reviewer"], owner="model-guard")
    response = dispatch_client.post(
        f"/agents/{agent_id}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "not-allowed",
            "ttl_sec": 60,
        },
    )
    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"].lower()
