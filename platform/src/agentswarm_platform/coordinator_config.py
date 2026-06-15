"""Coordinator parameters published on /platform/config (ADR 0010)."""

from __future__ import annotations

from agentswarm_platform.coordinator_plan import (
    ALLOWED_DEFERRED_TASK_TYPES,
    ALLOWED_IMMEDIATE_TASK_TYPES,
)


def public_parameters() -> dict[str, object]:
    return {
        "default_plan": "deterministic",
        "llm_planner": "optional_single_shot",
        "allowed_immediate_task_types": sorted(ALLOWED_IMMEDIATE_TASK_TYPES),
        "allowed_deferred_task_types": sorted(ALLOWED_DEFERRED_TASK_TYPES),
    }
