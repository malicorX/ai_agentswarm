from __future__ import annotations

from typing import Any

from agentswarm_platform.coordinator_plan import build_default_creative_goal_plan
from agentswarm_agents.git_capsule import execute_git_patch_capsule


def execute_capsule(assignment: dict[str, Any]) -> dict[str, Any]:
    """Run an assigned capsule in-process (mock LLM until local runtime is wired)."""
    task_type = assignment.get("task_type", "")
    capsule = assignment.get("capsule") or {}
    if task_type == "coordinator.decompose":
        return build_default_creative_goal_plan(
            {
                "goal_id": capsule.get("goal_id"),
                "brief": capsule.get("brief", ""),
                "rubric": capsule.get("rubric") or [{"id": "quality", "weight": 1.0}],
                "min_reviewers": int(capsule.get("min_reviewers", 3)),
            }
        )
    if task_type == "codewriter.patch":
        if isinstance(capsule.get("git"), dict):
            git_capsule = dict(capsule)
            git_capsule["task_id"] = assignment.get("task_id")
            return execute_git_patch_capsule(git_capsule)
        raise ValueError("codewriter.patch capsule requires git section in dispatch mode")
    if task_type == "creative.text":
        brief = capsule.get("brief", "creative work")
        return {
            "text": (
                f"Container poem for: {brief}\n"
                "Sandboxed lines emerge,\n"
                "Docker holds the spark,\n"
                "Dispatch sends the work,\n"
                "Credits mark the arc."
            ),
        }
    if task_type == "reviewer.subjective":
        rubric = capsule.get("rubric") or [{"id": "quality", "weight": 1.0}]
        scores = {str(item["id"]): 8.0 for item in rubric}
        return {
            "scores": scores,
            "rationale": "Container reviewer: solid craft and on-brief.",
        }
    if task_type == "reviewer.approve":
        return {"approved": True, "notes": "container approve"}
    return {"ok": True, "task_type": task_type}
