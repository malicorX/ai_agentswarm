from __future__ import annotations

import copy
import json
from typing import Any

from agentswarm_platform.hardware_gates import (
    high_risk_reviewer_min_vram_gb,
    high_risk_reviewer_replication_quorum,
    high_risk_reviewer_replication_slots,
    is_high_risk_goal,
)

ALLOWED_IMMEDIATE_TASK_TYPES = frozenset({"creative.text"})
ALLOWED_DEFERRED_TASK_TYPES = frozenset({"reviewer.subjective"})
ALLOWED_ENGINEERING_IMMEDIATE_TASK_TYPES = frozenset({"codewriter.patch"})
ALLOWED_ENGINEERING_DEFERRED_TASK_TYPES = frozenset(
    {"builder.compile", "tester.run", "reviewer.approve"}
)

DEFAULT_ENGINEERING_RUBRIC = [{"id": "quality", "weight": 1.0, "description": "Meets brief"}]


def git_in_container_enabled(goal: dict[str, Any]) -> bool:
    verification_spec = goal.get("verification_spec") or {}
    raw = verification_spec.get("git_in_container")
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def engineering_workspace_mode(goal: dict[str, Any]) -> str:
    """Resolve how engineering code is written and tested for a goal."""
    verification_spec = goal.get("verification_spec") or {}
    workspace = goal.get("workspace") or {}
    if workspace.get("mode") == "git" or verification_spec.get("workspace_mode") == "git":
        return "git"
    mode = str(verification_spec.get("workspace_mode", "local_fixture")).strip().lower()
    if mode == "sandbox":
        return "sandbox"
    if mode == "windows":
        return "windows"
    return "local_fixture"


def sandbox_build_capability(mode: str) -> str:
    if mode == "windows":
        return "sandbox.windows.build"
    return "sandbox.build"


def sandbox_test_capability(mode: str) -> str:
    if mode == "windows":
        return "sandbox.windows.test"
    return "sandbox.test"


def _engineering_patch_section(verification_spec: dict[str, Any]) -> dict[str, str]:
    fixture = str(verification_spec.get("fixture", "primes"))
    patch_file = str(verification_spec.get("patch_file", f"{fixture}.py"))
    return {
        "file": patch_file,
        "marker": "<!-- agentswarm:implement -->",
    }


def build_engineering_codewriter_capsule(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = goal["goal_id"]
    brief = goal["brief"]
    verification_spec = goal.get("verification_spec") or {
        "fixture": "primes",
        "lab": "engineering-lab",
    }
    mode = engineering_workspace_mode(goal)
    capsule: dict[str, Any] = {
        "goal_id": goal_id,
        "brief": brief,
        "patch": _engineering_patch_section(verification_spec),
    }
    fixture = str(verification_spec.get("fixture", "primes"))
    if mode == "git":
        workspace = goal.get("workspace") or {}
        capsule["git"] = {
            "repo_url": workspace["repo_url"],
            "default_branch": workspace.get("default_branch", "main"),
            "forge_type": workspace.get("forge_type", "git"),
        }
        capsule["lab"] = {"fixture": fixture}
        if git_in_container_enabled(goal):
            capsule["sandbox_git"] = True
    else:
        capsule["lab"] = {
            "fixture": fixture,
            "lab": verification_spec.get("lab", "engineering-lab"),
        }
    return capsule


def build_engineering_builder_deferred_spec(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = goal["goal_id"]
    verification_spec = goal.get("verification_spec") or {
        "fixture": "primes",
        "lab": "engineering-lab",
    }
    mode = engineering_workspace_mode(goal)
    return {
        "role": "builder",
        "capability_required": sandbox_build_capability(mode),
        "task_type": "builder.compile",
        "count": 1,
        "payload_template": {
            "goal_id": goal_id,
            "verification_spec": verification_spec,
            "capsule": {"verification_spec": verification_spec},
        },
        "constraints": {"exclude_worker": True},
    }


def build_engineering_tester_deferred_spec(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = goal["goal_id"]
    verification_spec = goal.get("verification_spec") or {
        "fixture": "primes",
        "lab": "engineering-lab",
    }
    mode = engineering_workspace_mode(goal)
    if mode in ("sandbox", "windows"):
        return {
            "role": "tester",
            "capability_required": sandbox_test_capability(mode),
            "task_type": "tester.run",
            "count": 1,
            "payload_template": {
                "goal_id": goal_id,
                "verification_spec": verification_spec,
                "capsule": {"verification_spec": verification_spec},
            },
            "constraints": {"exclude_worker": True},
        }
    if mode == "git":
        workspace = goal.get("workspace") or {}
        if git_in_container_enabled(goal):
            return {
                "role": "tester",
                "capability_required": "sandbox.test",
                "task_type": "tester.run",
                "count": 1,
                "payload_template": {
                    "goal_id": goal_id,
                    "verification_spec": {
                        **verification_spec,
                        "git_in_container": True,
                    },
                    "capsule": {
                        "git": workspace,
                        "verification_spec": {
                            **verification_spec,
                            "git_in_container": True,
                        },
                    },
                },
                "constraints": {"exclude_worker": True},
            }
        return {
            "role": "tester",
            "capability_required": "tester",
            "task_type": "tester.run",
            "count": 1,
            "payload_template": {
                "goal_id": goal_id,
                "verification_spec": verification_spec,
                "capsule": {"git": workspace},
            },
            "constraints": {"exclude_worker": True},
        }
    return {
        "role": "tester",
        "capability_required": "tester",
        "task_type": "tester.run",
        "count": 1,
        "payload_template": {
            "goal_id": goal_id,
            "verification_spec": verification_spec,
        },
        "constraints": {"exclude_worker": True},
    }


def build_engineering_reviewer_deferred_spec(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = goal["goal_id"]
    brief = goal["brief"]
    constraints: dict[str, Any] = {
        "exclude_poster": True,
        "exclude_worker": True,
    }
    payload_template: dict[str, Any] = {
        "goal_id": goal_id,
        "brief": brief,
    }
    if is_high_risk_goal(goal):
        constraints["min_reviewer_vram_gb"] = high_risk_reviewer_min_vram_gb()
        payload_template["replication"] = {
            "slots": high_risk_reviewer_replication_slots(),
            "quorum": high_risk_reviewer_replication_quorum(),
        }
    return {
        "role": "reviewer",
        "capability_required": "reviewer",
        "task_type": "reviewer.approve",
        "count": 1,
        "payload_template": payload_template,
        "constraints": constraints,
    }


def build_default_engineering_goal_plan(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = goal["goal_id"]
    mode = engineering_workspace_mode(goal)
    deferred_pool_needs: list[dict[str, Any]] = []
    if mode in ("sandbox", "windows"):
        deferred_pool_needs.append(
            {
                "after_task_type": "codewriter.patch",
                "spec": build_engineering_builder_deferred_spec(goal),
            }
        )
        tester_after = "builder.compile"
    else:
        tester_after = "codewriter.patch"
    deferred_pool_needs.extend(
        [
            {
                "after_task_type": tester_after,
                "spec": build_engineering_tester_deferred_spec(goal),
            },
            {
                "after_task_type": "tester.run",
                "spec": build_engineering_reviewer_deferred_spec(goal),
            },
        ]
    )
    return {
        "goal_id": goal_id,
        "pool_needs": [
            {
                "role": "codewriter",
                "capability_required": "codewriter",
                "task_type": "codewriter.patch",
                "payload": {
                    "goal_id": goal_id,
                    "capsule": build_engineering_codewriter_capsule(goal),
                },
            }
        ],
        "deferred_pool_needs": deferred_pool_needs,
    }


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


def default_plan_for_goal(goal: dict[str, Any]) -> dict[str, Any]:
    if goal.get("goal_kind") == "engineering":
        return build_default_engineering_goal_plan(goal)
    return build_default_creative_goal_plan(goal)


def validate_coordinator_plan(
    result: dict[str, Any],
    *,
    goal_id: str,
    goal_kind: str = "creative",
) -> dict[str, Any]:
    if result.get("goal_id") != goal_id:
        raise ValueError("coordinator plan goal_id must match task goal_id")
    pool_needs = result.get("pool_needs")
    if not isinstance(pool_needs, list) or not pool_needs:
        raise ValueError("coordinator result requires non-empty pool_needs list")
    deferred = result.get("deferred_pool_needs", [])
    if deferred is not None and not isinstance(deferred, list):
        raise ValueError("deferred_pool_needs must be a list when provided")
    allowed_immediate = (
        ALLOWED_ENGINEERING_IMMEDIATE_TASK_TYPES
        if goal_kind == "engineering"
        else ALLOWED_IMMEDIATE_TASK_TYPES
    )
    allowed_deferred = (
        ALLOWED_ENGINEERING_DEFERRED_TASK_TYPES
        if goal_kind == "engineering"
        else ALLOWED_DEFERRED_TASK_TYPES
    )
    for index, need in enumerate(pool_needs):
        _validate_pool_need_spec(
            need,
            label=f"pool_needs[{index}]",
            deferred=False,
            allowed_immediate=allowed_immediate,
            allowed_deferred=allowed_deferred,
        )
    for index, entry in enumerate(deferred or []):
        _validate_deferred_entry(
            entry,
            label=f"deferred_pool_needs[{index}]",
            allowed_deferred=allowed_deferred,
        )
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
    allowed_immediate: frozenset[str] | None = None,
    allowed_deferred: frozenset[str] | None = None,
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
    immediate = allowed_immediate if allowed_immediate is not None else ALLOWED_IMMEDIATE_TASK_TYPES
    deferred_types = allowed_deferred if allowed_deferred is not None else ALLOWED_DEFERRED_TASK_TYPES
    allowed = deferred_types if deferred else immediate
    if task_type not in allowed:
        raise ValueError(f"{label}.task_type {task_type!r} is not allowed for coordinator")
    if not isinstance(payload, dict):
        raise ValueError(f"{label}.payload must be an object")
    constraints = need.get("constraints", {})
    if constraints is not None and not isinstance(constraints, dict):
        raise ValueError(f"{label}.constraints must be an object")


def _validate_deferred_entry(
    entry: Any,
    *,
    label: str,
    allowed_deferred: frozenset[str] | None = None,
) -> None:
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
        allowed_deferred=allowed_deferred,
    )
    if "payload_template" not in spec or not isinstance(spec["payload_template"], dict):
        raise ValueError(f"{label}.spec.payload_template must be an object")


def materialize_deferred_payload(
    template: dict[str, Any],
    *,
    goal: dict[str, Any],
    parent_test_result: dict[str, Any] | None = None,
    parent_task_id: str | None = None,
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
    verification_spec = goal.get("verification_spec")
    if isinstance(verification_spec, dict):
        payload.setdefault("verification_spec", verification_spec)
        if "verification_spec" not in capsule:
            capsule["verification_spec"] = verification_spec
    workspace_ref = goal.get("workspace_ref")
    if workspace_ref:
        payload["workspace_ref"] = workspace_ref
        capsule["workspace_ref"] = workspace_ref
        if isinstance(capsule.get("git"), dict):
            capsule["parent_git_artifact"] = {"commit_sha": workspace_ref}
    if goal.get("goal_kind") == "engineering" and isinstance(artifact, str):
        try:
            parsed = json.loads(artifact)
            if isinstance(parsed, dict) and parsed.get("git_artifact"):
                capsule["parent_git_artifact"] = parsed["git_artifact"]
                if not workspace_ref and parsed.get("workspace_ref"):
                    ref = str(parsed["workspace_ref"])
                    payload["workspace_ref"] = ref
                    capsule["workspace_ref"] = ref
        except (json.JSONDecodeError, TypeError):
            pass
    if parent_test_result is not None:
        payload["test_result"] = parent_test_result
        capsule["test_result"] = parent_test_result
    if parent_task_id:
        payload["parent_task_id"] = parent_task_id
    return payload


def goal_allows_same_agent_pipeline(goal: dict[str, Any]) -> bool:
    """Single-machine volunteers may run codewriter → tester → reviewer on one agent."""
    spec = goal.get("verification_spec") or {}
    explicit = spec.get("solo_pipeline")
    if explicit is True:
        return True
    if explicit is False:
        return False
    owners = goal.get("dispatch_include_owners") or []
    return not owners


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
    same_agent_pipeline = goal_allows_same_agent_pipeline(goal)
    if resolved.pop("exclude_poster", False):
        exclude_owners.append(poster_owner)
    if same_agent_pipeline:
        resolved.pop("exclude_worker", None)
    elif resolved.pop("exclude_worker", False) and worker_agent_id:
        exclude_agent_ids.append(worker_agent_id)
    exclude_agent_ids.append(goal["poster_agent_id"])
    if worker_agent_id and not same_agent_pipeline:
        exclude_agent_ids.append(worker_agent_id)
    deduped_owners = list(dict.fromkeys(exclude_owners))
    deduped_agents = list(dict.fromkeys(exclude_agent_ids))
    include_owners = [str(item) for item in resolved.pop("include_owners", [])]
    goal_include = goal.get("dispatch_include_owners") or []
    include_owners.extend(str(item) for item in goal_include)
    deduped_include = list(dict.fromkeys(include_owners))
    payload = {
        **resolved,
        "exclude_owners": deduped_owners,
        "exclude_agent_ids": deduped_agents,
    }
    if deduped_include:
        payload["include_owners"] = deduped_include
    return payload
