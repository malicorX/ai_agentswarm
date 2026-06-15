from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.ollama_executor import (
    execute_capsule_with_ollama,
    ollama_available,
    ollama_capsule_executor,
    ollama_model_name,
    validate_ollama_endpoint,
)


def test_validate_ollama_endpoint_rejects_remote_host() -> None:
    with pytest.raises(ValueError, match="localhost"):
        validate_ollama_endpoint("http://192.168.1.10:11434")


def test_validate_ollama_endpoint_accepts_loopback() -> None:
    assert validate_ollama_endpoint("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"


def test_ollama_model_name_prefers_explicit_field() -> None:
    entry = {"id": "ollama/llama3.2", "ollama_model": "llama3.2:latest"}
    assert ollama_model_name(entry) == "llama3.2:latest"


def test_ollama_model_name_derives_from_id() -> None:
    entry = {"id": "ollama/llama3.2"}
    assert ollama_model_name(entry) == "llama3.2"


def test_ollama_available_checks_tags_endpoint() -> None:
    mock_response = MagicMock(status_code=200)
    with patch("agentswarm_agents.ollama_executor.httpx.get", return_value=mock_response) as get:
        assert ollama_available("http://127.0.0.1:11434") is True
    get.assert_called_once_with("http://127.0.0.1:11434/api/tags", timeout=5.0)


def test_execute_capsule_with_ollama_creative_text() -> None:
    model_entry = {
        "id": "ollama/llama3.2",
        "endpoint": "http://127.0.0.1:11434",
        "ollama_model": "llama3.2",
    }
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "Moonlight on the volunteer mesh."}
    }
    with patch("agentswarm_agents.ollama_executor.httpx.post", return_value=mock_response) as post:
        result = execute_capsule_with_ollama(
            {
                "task_type": "creative.text",
                "capsule": {"brief": "A short poem about dispatch"},
            },
            model_entry=model_entry,
        )
    assert result == {"text": "Moonlight on the volunteer mesh."}
    post.assert_called_once()
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "llama3.2"
    assert payload["stream"] is False


def test_execute_capsule_with_ollama_reviewer_subjective_parses_json() -> None:
    model_entry = {
        "id": "ollama/llama3.2",
        "endpoint": "http://127.0.0.1:11434",
        "ollama_model": "llama3.2",
    }
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {
            "content": '{"scores": {"quality": 8.5}, "rationale": "Strong imagery."}'
        }
    }
    with patch("agentswarm_agents.ollama_executor.httpx.post", return_value=mock_response):
        result = execute_capsule_with_ollama(
            {
                "task_type": "reviewer.subjective",
                "capsule": {
                    "brief": "Poem task",
                    "rubric": [{"id": "quality", "weight": 1.0}],
                    "artifact_text": "Lines of code at night.",
                },
            },
            model_entry=model_entry,
        )
    assert result["scores"] == {"quality": 8.5}
    assert result["rationale"] == "Strong imagery."


def test_execute_capsule_with_ollama_falls_back_for_coordinator() -> None:
    model_entry = {"id": "ollama/llama3.2", "endpoint": "http://127.0.0.1:11434"}
    result = execute_capsule_with_ollama(
        {
            "task_type": "coordinator.decompose",
            "capsule": {
                "goal_id": "goal-1",
                "brief": "Write a poem",
                "rubric": [{"id": "quality", "weight": 1.0}],
                "min_reviewers": 2,
            },
        },
        model_entry=model_entry,
    )
    assert result["goal_id"] == "goal-1"
    assert result["pool_needs"][0]["task_type"] == "creative.text"


def test_ollama_capsule_executor_verifies_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    from agentswarm_platform.assignment_signing import sign_assignment

    model_entry = {"id": "ollama/llama3.2", "endpoint": "http://127.0.0.1:11434"}
    executor = ollama_capsule_executor("agent-1", model_entry=model_entry)
    assignment = {
        "lease_id": "lease-1",
        "task_id": "task-1",
        "task_type": "creative.text",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "capsule": {"brief": "test"},
        "assignment_signature": sign_assignment(
            {
                "lease_id": "lease-1",
                "agent_id": "agent-1",
                "task_id": "task-1",
                "expires_at": "2030-01-01T00:00:00+00:00",
            }
        ),
    }
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": "hello"}}
    with patch("agentswarm_agents.ollama_executor.httpx.post", return_value=mock_response):
        assert executor(assignment) == {"text": "hello"}


def test_ollama_capsule_executor_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    executor = ollama_capsule_executor("agent-1", model_entry={"id": "ollama/llama3.2"})
    with pytest.raises(ValueError, match="signature"):
        executor(
            {
                "lease_id": "lease-1",
                "task_id": "task-1",
                "task_type": "creative.text",
                "expires_at": "2030-01-01T00:00:00+00:00",
                "assignment_signature": "bad",
                "capsule": {},
            }
        )
