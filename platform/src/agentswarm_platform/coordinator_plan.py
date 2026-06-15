from __future__ import annotations

import copy
from typing import Any

ALLOWED_IMMEDIATE_TASK_TYPES = frozenset({"creative.text"})
ALLOWED_DEFERRED_TASK_TYPES = frozenset({"reviewer.subjective"})


def build_default_creative_goal_plan(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = goal["goal_id"]
    brief = goal["brief"]
    rubric = goal["rubric"]
    min_reviewers = int(goal["min_reviewers"])
    return {
        "goal_id": goal_id,
        "pool_needs": [
            {
                "role": "creative",
                "capability_required": "creative",
                "task_type": "creative.text",
                "payload": {
                    "goal_id": goal_id,
                    "capsule": {
                        "goal_id": goal_id,
                        "brief": brief,
                        "rubric": rubric,
                    },
                },
            }
        ],
        "deferred_pool_needs": [
            {
                "after_task_type": "creative.text",
                "spec": {
                    "role": "reviewer",
                    "capability_required": "reviewer",
                    "task_type": "reviewer.subjective",
                    "count": min_reviewers,
                    "payload_template": {
                        "goal_id": goal_id,
                        "capsule": {
                            "goal_id": goal_id,
                            "brief": brief,
                            "rubric": rubric,
                        },
                    },
                    "constraints": {
                        "exclude_poster": True,
                        "exclude_worker": True,
                    },
                },
            }
        ],
    }


def validate_coordinator_plan(result: dict[str, Any], *, goal_id: str) -> dict[str, Any]:
    if result.get("goal_id") != goal_id:
        raise ValueError("coordinator plan goal_id must match task goal_id")
    pool_needs = result.get("pool_needs")
    if not isinstance(pool_needs, list) or not pool_needs:
        raise ValueError("coordinator result requires non-empty pool_needs list")
    deferred = result.get("deferred_pool_needs", [])
    if deferred is not None and not isinstance(deferred, list):
        raise ValueError("deferred_pool_needs must be a list when provided")
    for index, need in enumerate(pool_needs):
        _validate_pool_need_spec(need, label=f"pool_needs[{index}]", deferred=False)
    for index, entry in enumerate(deferred or []):
        _validate_deferred_entry(entry, label=f"deferred_pool_needs[{index}]")
    return {
        "goal_id": goal_id,
        "pool_needs": pool_needs,
        "deferred_pool_needs": deferred or [],
    }


def _validate_pool_need_spec(
    need: Any,
    *,
    label: str,
    deferred: bool,
) -> None:
    if not isinstance(need, dict):
        raise ValueError(f"{label} must be an object")
    role = need.get("role")
    capability = need.get("capability_required")
    task_type = need.get("task_type")
    payload = need.get("payload")
    if not isinstance(role, str) or not role.strip():
        raise ValueError(f"{label}.role is required")
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError(f"{label}.capability_required is required")
    if not isinstance(task_type, str) or not task_type.strip():
        raise ValueError(f"{label}.task_type is required")
    allowed = ALLOWED_DEFERRED_TASK_TYPES if deferred else ALLOWED_IMMEDIATE_TASK_TYPES
    if task_type not in allowed:
        raise ValueError(f"{label}.task_type {task_type!r} is not allowed for coordinator")
    if not isinstance(payload, dict):
        raise ValueError(f"{label}.payload must be an object")
    constraints = need.get("constraints", {})
    if constraints is not None and not isinstance(constraints, dict):
        raise ValueError(f"{label}.constraints must be an object")


def _validate_deferred_entry(entry: Any, *, label: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} must be an object")
    after_task_type = entry.get("after_task_type")
    if not isinstance(after_task_type, str) or not after_task_type.strip():
        raise ValueError(f"{label}.after_task_type is required")
    spec = entry.get("spec")
    if not isinstance(spec, dict):
        raise ValueError(f"{label}.spec is required")
    count = spec.get("count", 1)
    if not isinstance(count, int) or count < 1:
        raise ValueError(f"{label}.spec.count must be a positive integer")
    _validate_pool_need_spec(
        {**spec, "payload": spec.get("payload_template")},
        label=f"{label}.spec",
        deferred=True,
    )
    if "payload_template" not in spec or not isinstance(spec["payload_template"], dict):
        raise ValueError(f"{label}.spec.payload_template must be an object")


def materialize_deferred_payload(
    template: dict[str, Any],
    *,
    goal: dict[str, Any],
) -> dict[str, Any]:
    payload = copy.deepcopy(template)
    payload["goal_id"] = goal["goal_id"]
    capsule = payload.setdefault("capsule", {})
    if not isinstance(capsule, dict):
        raise ValueError("payload_template.capsule must be an object")
    capsule["goal_id"] = goal["goal_id"]
    capsule["brief"] = goal["brief"]
    capsule["rubric"] = goal["rubric"]
    artifact = goal.get("artifact_text")
    if artifact:
        capsule["artifact_text"] = artifact
    return payload


def resolve_pool_need_constraints(
    constraints: dict[str, Any] | None,
    *,
    goal: dict[str, Any],
    poster_owner: str,
    worker_agent_id: str | None,
) -> dict[str, Any]:
    resolved = dict(constraints or {})
    exclude_owners = [str(item) for item in resolved.pop("exclude_owners", [])]
    exclude_agent_ids = [str(item) for item in resolved.pop("exclude_agent_ids", [])]
    if resolved.pop("exclude_poster", False):
        exclude_owners.append(poster_owner)
    if resolved.pop("exclude_worker", False) and worker_agent_id:
        exclude_agent_ids.append(worker_agent_id)
    exclude_agent_ids.append(goal["poster_agent_id"])
    if worker_agent_id:
        exclude_agent_ids.append(worker_agent_id)
    deduped_owners = list(dict.fromkeys(exclude_owners))
    deduped_agents = list(dict.fromkeys(exclude_agent_ids))
    return {
        **resolved,
        "exclude_owners": deduped_owners,
        "exclude_agent_ids": deduped_agents,
    }
