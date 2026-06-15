from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.coordinator_planner import build_deterministic_coordinator_plan
from agentswarm_agents.ollama_executor import execute_capsule_with_ollama


def test_ollama_coordinator_uses_llm_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_COORDINATOR_LLM", "1")
    model_entry = {"id": "ollama/llama3.2", "endpoint": "http://127.0.0.1:11434"}
    plan = build_deterministic_coordinator_plan(
        {
            "goal_id": "goal-1",
            "brief": "Write a poem",
            "rubric": [{"id": "quality", "weight": 1.0}],
            "min_reviewers": 2,
        }
    )
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": json.dumps(plan)}}
    with patch("agentswarm_agents.ollama_executor.httpx.post", return_value=mock_response):
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


def test_ollama_coordinator_falls_back_on_invalid_llm_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_COORDINATOR_LLM", "1")
    model_entry = {"id": "ollama/llama3.2", "endpoint": "http://127.0.0.1:11434"}
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": "not json"}}
    with patch("agentswarm_agents.ollama_executor.httpx.post", return_value=mock_response):
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
    assert result["deferred_pool_needs"][0]["spec"]["count"] == 2
