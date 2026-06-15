from __future__ import annotations

import pytest

from agentswarm_platform.coordinator_plan import (
    build_default_creative_goal_plan,
    materialize_deferred_payload,
    resolve_pool_need_constraints,
    validate_coordinator_plan,
)


GOAL = {
    "goal_id": "goal-abc",
    "poster_agent_id": "agent-poster",
    "brief": "Write a poem",
    "rubric": [{"id": "quality", "weight": 1.0}],
    "min_reviewers": 3,
}


def test_build_default_creative_goal_plan() -> None:
    plan = build_default_creative_goal_plan(GOAL)
    assert plan["goal_id"] == "goal-abc"
    assert len(plan["pool_needs"]) == 1
    assert plan["pool_needs"][0]["task_type"] == "creative.text"
    assert len(plan["deferred_pool_needs"]) == 1
    assert plan["deferred_pool_needs"][0]["after_task_type"] == "creative.text"
    assert plan["deferred_pool_needs"][0]["spec"]["count"] == 3


def test_validate_coordinator_plan_rejects_missing_pool_needs() -> None:
    with pytest.raises(ValueError, match="pool_needs"):
        validate_coordinator_plan({"goal_id": "goal-abc"}, goal_id="goal-abc")


def test_validate_coordinator_plan_rejects_disallowed_task_type() -> None:
    plan = build_default_creative_goal_plan(GOAL)
    plan["pool_needs"][0]["task_type"] = "codewriter.patch"
    with pytest.raises(ValueError, match="not allowed"):
        validate_coordinator_plan(plan, goal_id="goal-abc")


def test_materialize_deferred_payload_injects_artifact() -> None:
    template = {
        "goal_id": "goal-abc",
        "capsule": {"goal_id": "goal-abc", "brief": "Write a poem"},
    }
    payload = materialize_deferred_payload(
        template,
        goal={**GOAL, "artifact_text": "Poem body"},
    )
    assert payload["capsule"]["artifact_text"] == "Poem body"


def test_resolve_pool_need_constraints_exclude_flags() -> None:
    resolved = resolve_pool_need_constraints(
        {"exclude_poster": True, "exclude_worker": True},
        goal=GOAL,
        poster_owner="poster-owner",
        worker_agent_id="agent-worker",
    )
    assert "poster-owner" in resolved["exclude_owners"]
    assert "agent-poster" in resolved["exclude_agent_ids"]
    assert "agent-worker" in resolved["exclude_agent_ids"]


def test_resolve_pool_need_constraints_merges_goal_include_owners() -> None:
    resolved = resolve_pool_need_constraints(
        {"exclude_poster": True},
        goal={**GOAL, "dispatch_include_owners": ["demo-coordinator-run"]},
        poster_owner="poster-owner",
        worker_agent_id=None,
    )
    assert resolved["include_owners"] == ["demo-coordinator-run"]
