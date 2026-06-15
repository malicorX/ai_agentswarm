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
) -> bool:
    if not hardware_gates_enforced():
        return True
    if vram_gb is None:
        return False
    return float(vram_gb) >= required_reviewer_vram_gb(model_id)


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


def public_parameters() -> dict[str, Any]:
    return {
        "enforced": hardware_gates_enforced(),
        "reviewer_min_vram_gb": reviewer_min_vram_gb(),
    }
