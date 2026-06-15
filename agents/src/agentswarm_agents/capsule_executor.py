from __future__ import annotations

from typing import Any


def execute_capsule(assignment: dict[str, Any]) -> dict[str, Any]:
    """Run an assigned capsule in-process (mock LLM until local runtime is wired)."""
    task_type = assignment.get("task_type", "")
    capsule = assignment.get("capsule") or {}
    if task_type == "coordinator.decompose":
        goal_id = capsule.get("goal_id")
        return {"goal_id": goal_id, "acknowledged": True}
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
