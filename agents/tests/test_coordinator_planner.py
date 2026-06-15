from __future__ import annotations

import pytest

from agentswarm_agents.coordinator_planner import (
    build_deterministic_coordinator_plan,
    coordinator_llm_enabled,
    goal_from_capsule,
)


CAPSULE = {
    "goal_id": "goal-abc",
    "brief": "Write a haiku",
    "rubric": [{"id": "quality", "weight": 1.0}],
    "min_reviewers": 2,
}


def test_goal_from_capsule_defaults() -> None:
    goal = goal_from_capsule({"goal_id": "g1", "brief": "test"})
    assert goal["goal_id"] == "g1"
    assert goal["min_reviewers"] == 3
    assert goal["rubric"][0]["id"] == "quality"


def test_build_deterministic_coordinator_plan() -> None:
    plan = build_deterministic_coordinator_plan(CAPSULE)
    assert plan["goal_id"] == "goal-abc"
    assert plan["pool_needs"][0]["task_type"] == "creative.text"
    assert plan["deferred_pool_needs"][0]["spec"]["count"] == 2


def test_coordinator_llm_enabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_COORDINATOR_LLM", raising=False)
    assert coordinator_llm_enabled() is False
    monkeypatch.setenv("AGENTSWARM_COORDINATOR_LLM", "1")
    assert coordinator_llm_enabled() is True
