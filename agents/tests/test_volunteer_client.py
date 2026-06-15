from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.volunteer_client import (
    VolunteerClient,
    VolunteerConfig,
    assert_dispatch_mode,
    assert_platform_model_allowlist,
    resolve_executor,
)


def test_assert_dispatch_mode_requires_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"assignment_mode": "pull"}
    mock_response.raise_for_status = MagicMock()
    with patch("agentswarm_agents.volunteer_client.httpx.get", return_value=mock_response):
        with pytest.raises(RuntimeError, match="dispatch"):
            assert_dispatch_mode("http://127.0.0.1:8000")


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


def test_volunteer_run_once_verifies_and_submits(monkeypatch: pytest.MonkeyPatch) -> None:
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
    mock_client.submit_assignment.assert_called_once()
