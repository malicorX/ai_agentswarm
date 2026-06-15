from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from agentswarm_agents.volunteer_client import (
    VolunteerClient,
    VolunteerConfig,
    assert_dispatch_mode,
    assert_dispatch_mode_config,
    assert_platform_model_allowlist,
    platform_assignment_mode,
    resolve_executor,
)


def test_assert_dispatch_mode_requires_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"assignment_mode": "pull"}
    mock_response.raise_for_status = MagicMock()
    with patch("agentswarm_agents.volunteer_client.httpx.get", return_value=mock_response):
        with pytest.raises(RuntimeError, match="maintainer/dev"):
            assert_dispatch_mode("http://127.0.0.1:8000")


def test_platform_assignment_mode_prefers_assignment_block() -> None:
    config = {
        "assignment_mode": "pull",
        "assignment": {"mode": "dispatch"},
    }
    assert platform_assignment_mode(config) == "dispatch"


def test_assert_dispatch_mode_config_accepts_assignment_block() -> None:
    assert_dispatch_mode_config({"assignment": {"mode": "dispatch"}})


def test_assert_platform_model_allowlist_rejects_unknown() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "models": {"allowlist": [{"id": "llm-mock-v1"}]},
    }
    mock_response.raise_for_status = MagicMock()
    with patch("agentswarm_agents.volunteer_client.httpx.get", return_value=mock_response):
        with pytest.raises(RuntimeError, match="platform allowlist"):
            assert_platform_model_allowlist("http://127.0.0.1:8000", "other-model")


def test_resolve_executor_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ALLOWLIST_SKIP", "1")
    config = VolunteerConfig(
        agent_name="test",
        base_url="http://127.0.0.1:8000",
        owner="owner",
        capabilities=["reviewer"],
        model_id="llm-mock-v1",
    )
    executor = resolve_executor(config, "agent-1")
    result = executor(
        {
            "task_type": "reviewer.subjective",
            "capsule": {"rubric": [{"id": "quality", "weight": 1.0}]},
        }
    )
    assert "scores" in result


def test_resolve_executor_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_ALLOWLIST_SKIP", raising=False)
    config = VolunteerConfig(
        agent_name="test",
        base_url="http://127.0.0.1:8000",
        owner="owner",
        capabilities=["creative"],
        model_id="ollama/llama3.2",
    )
    with (
        patch("agentswarm_agents.volunteer_client.ollama_available", return_value=True),
        patch(
            "agentswarm_agents.volunteer_client.ollama_capsule_executor",
            return_value=lambda assignment: {"text": "ollama"},
        ) as factory,
    ):
        executor = resolve_executor(config, "agent-ollama")
    factory.assert_called_once()
    assert executor({"task_type": "creative.text", "capsule": {}}) == {"text": "ollama"}


def test_resolve_executor_ollama_requires_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_ALLOWLIST_SKIP", raising=False)
    config = VolunteerConfig(
        agent_name="test",
        base_url="http://127.0.0.1:8000",
        owner="owner",
        capabilities=["creative"],
        model_id="ollama/llama3.2",
    )
    with patch("agentswarm_agents.volunteer_client.ollama_available", return_value=False):
        with pytest.raises(RuntimeError, match="Ollama"):
            resolve_executor(config, "agent-ollama")


def test_volunteer_run_once_heartbeats_busy_before_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    monkeypatch.setenv("AGENTSWARM_ALLOWLIST_SKIP", "1")
    from agentswarm_platform.assignment_signing import sign_assignment

    config = VolunteerConfig(
        agent_name="test",
        base_url="http://127.0.0.1:8000",
        owner="owner",
        capabilities=["reviewer"],
        model_id="llm-mock-v1",
        wait_timeout_sec=0.01,
        poll_sec=0.01,
    )
    volunteer = VolunteerClient(config)
    mock_client = MagicMock()
    mock_client.agent_id = "agent-1"
    assignment = {
        "lease_id": "lease-1",
        "task_id": "task-1",
        "task_type": "reviewer.subjective",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "claim_token": "claim",
        "capsule": {"rubric": [{"id": "quality", "weight": 1.0}]},
        "assignment_signature": sign_assignment(
            {
                "lease_id": "lease-1",
                "agent_id": "agent-1",
                "task_id": "task-1",
                "expires_at": "2030-01-01T00:00:00+00:00",
            }
        ),
    }
    mock_client.wait_for_assignment.return_value = assignment
    mock_client.submit_assignment.return_value = "sub-1"
    volunteer._client = mock_client
    volunteer._executor = lambda assignment: {"scores": {"quality": 8.0}, "rationale": "ok"}

    assert volunteer.run_once() is True
    busy_calls = [
        call
        for call in mock_client.heartbeat.call_args_list
        if call.kwargs.get("status") == "busy"
    ]
    assert len(busy_calls) == 1
    mock_client.submit_assignment.assert_called_once()


def test_dispatch_client_submit_includes_platform_detail() -> None:
    from agentswarm_agents.dispatch_client import DispatchClient

    client = DispatchClient("http://127.0.0.1:8000", "agent-1", b"\x01" * 32)
    mock_response = MagicMock()
    mock_response.is_error = True
    mock_response.status_code = 400
    mock_response.text = "raw"
    mock_response.json.return_value = {"detail": "task not in claimed state"}
    client._http.post = MagicMock(return_value=mock_response)

    with pytest.raises(RuntimeError, match="task not in claimed state"):
        client.submit_assignment(
            {"claim_token": "tok", "task_id": "task-1"},
            {"scores": {"quality": 8.0}},
        )
