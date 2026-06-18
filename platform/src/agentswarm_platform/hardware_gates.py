"""Server-side volunteer hardware gates (P9.1)."""

from __future__ import annotations

import os
from typing import Any

from agentswarm_platform.model_allowlist import get_model_entry, load_model_allowlist


def hardware_gates_enforced() -> bool:
    raw = os.environ.get("AGENTSWARM_HARDWARE_GATES_ENFORCE", "").lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return False


def reviewer_min_vram_gb() -> float:
    override = os.environ.get("AGENTSWARM_REVIEWER_MIN_VRAM_GB", "").strip()
    if override:
        return float(override)
    data = load_model_allowlist()
    hardware = data.get("hardware")
    if isinstance(hardware, dict) and hardware.get("reviewer_min_vram_gb") is not None:
        return float(hardware["reviewer_min_vram_gb"])
    return 6.0


def high_risk_reviewer_min_vram_gb() -> float:
    override = os.environ.get("AGENTSWARM_HIGH_RISK_REVIEWER_MIN_VRAM_GB", "").strip()
    if override:
        return float(override)
    return 12.0


def goal_risk_level(goal: dict[str, Any]) -> str:
    spec = goal.get("verification_spec")
    if not isinstance(spec, dict):
        return "normal"
    level = str(spec.get("risk_level", "normal")).strip().lower()
    return "high" if level == "high" else "normal"


def is_high_risk_goal(goal: dict[str, Any]) -> bool:
    return goal_risk_level(goal) == "high"


def effective_reviewer_min_vram_gb(
    *,
    model_id: str | None,
    constraints: dict[str, Any] | None = None,
) -> float:
    required = required_reviewer_vram_gb(model_id)
    if constraints:
        raw = constraints.get("min_reviewer_vram_gb")
        if raw is not None:
            required = max(required, float(raw))
    return required


def model_min_vram_gb(model_id: str | None) -> float:
    if not model_id:
        return 0.0
    entry = get_model_entry(model_id)
    if entry is None:
        return 0.0
    raw = entry.get("min_vram_gb")
    if raw is None:
        return 0.0
    return float(raw)


def required_reviewer_vram_gb(model_id: str | None) -> float:
    return max(reviewer_min_vram_gb(), model_min_vram_gb(model_id))


def agent_meets_reviewer_hardware(
    *,
    model_id: str | None,
    vram_gb: float | None,
    constraints: dict[str, Any] | None = None,
) -> bool:
    if not hardware_gates_enforced():
        return True
    if vram_gb is None:
        return False
    required = effective_reviewer_min_vram_gb(model_id=model_id, constraints=constraints)
    return float(vram_gb) >= required


def validate_presence_hardware(
    capabilities: list[str],
    *,
    model_id: str | None,
    vram_gb: float | None,
) -> None:
    if not hardware_gates_enforced():
        return
    if "reviewer" not in capabilities:
        return
    if vram_gb is None:
        raise ValueError(
            "reviewer presence requires vram_gb when hardware gates are enforced"
        )
    required = required_reviewer_vram_gb(model_id)
    if float(vram_gb) < required:
        raise ValueError(
            f"reviewer vram_gb {vram_gb} is below required minimum {required} "
            f"for model_id {model_id!r}"
        )


def high_risk_reviewer_replication_slots() -> int:
    raw = os.environ.get("AGENTSWARM_HIGH_RISK_REVIEWER_SLOTS", "2").strip()
    return max(2, int(raw))


def high_risk_reviewer_replication_quorum() -> int:
    raw = os.environ.get("AGENTSWARM_HIGH_RISK_REVIEWER_QUORUM", "2").strip()
    slots = high_risk_reviewer_replication_slots()
    return min(max(2, int(raw)), slots)


def public_parameters() -> dict[str, Any]:
    return {
        "enforced": hardware_gates_enforced(),
        "reviewer_min_vram_gb": reviewer_min_vram_gb(),
        "high_risk_reviewer_min_vram_gb": high_risk_reviewer_min_vram_gb(),
        "high_risk_reviewer_replication_slots": high_risk_reviewer_replication_slots(),
        "high_risk_reviewer_replication_quorum": high_risk_reviewer_replication_quorum(),
    }
