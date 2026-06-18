"""Coordinator plan helpers for volunteer clients (ADR 0010)."""

from __future__ import annotations

import os
from typing import Any

from agentswarm_platform.coordinator_plan import build_default_creative_goal_plan


def coordinator_llm_enabled() -> bool:
    return os.environ.get("AGENTSWARM_COORDINATOR_LLM", "").lower() in (
        "1",
        "true",
        "yes",
    )

def goal_from_capsule(capsule: dict[str, Any]) -> dict[str, Any]:
    rubric = capsule.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        rubric = [{"id": "quality", "weight": 1.0}]
    goal: dict[str, Any] = {
        "goal_id": str(capsule["goal_id"]),
        "brief": str(capsule.get("brief", "")),
        "rubric": rubric,
        "min_reviewers": int(capsule.get("min_reviewers", 3)),
        "goal_kind": str(capsule.get("goal_kind", "creative")),
    }
    verification_spec = capsule.get("verification_spec")
    if isinstance(verification_spec, dict):
        goal["verification_spec"] = verification_spec
    workspace = capsule.get("workspace")
    if isinstance(workspace, dict):
        goal["workspace"] = workspace
    return goal


def build_deterministic_coordinator_plan(capsule: dict[str, Any]) -> dict[str, Any]:
    """Default single-step planner — no LLM (platform may also apply this server-side)."""
    goal = goal_from_capsule(capsule)
    if goal.get("goal_kind") == "engineering":
        from agentswarm_platform.coordinator_plan import build_default_engineering_goal_plan

        return build_default_engineering_goal_plan(goal)
    from agentswarm_platform.coordinator_plan import build_default_creative_goal_plan

    return build_default_creative_goal_plan(goal)
