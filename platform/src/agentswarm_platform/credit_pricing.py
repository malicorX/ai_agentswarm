"""Per-task-class credit pricing (post burn, reviewer reward, verify mint)."""

from __future__ import annotations

import json
import os
from typing import Any

from agentswarm_platform.credits_ledger import credits_enabled, initial_credits

PricingEntry = dict[str, float]

_DEFAULT_TABLE: dict[str, PricingEntry] = {
    "creative.goal": {"post_cost": 50.0, "reviewer_reward": 15.0},
    "creative.text": {"verify_mint": 10.0},
    "reviewer.subjective": {"reviewer_reward": 15.0},
    "coordinator.decompose": {"verify_mint": 5.0},
    "codewriter.patch": {"post_cost": 20.0},
    "git.patch": {"post_cost": 30.0},
}


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return float(raw)


def load_pricing_table() -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = {
        task_class: dict(entry) for task_class, entry in _DEFAULT_TABLE.items()
    }
    goal_override = _env_float("AGENTSWARM_CREDITS_GOAL_COST")
    if goal_override is not None:
        table["creative.goal"]["post_cost"] = goal_override
    reward_override = _env_float("AGENTSWARM_CREDITS_REVIEWER_REWARD")
    if reward_override is not None:
        table["creative.goal"]["reviewer_reward"] = reward_override
        table["reviewer.subjective"]["reviewer_reward"] = reward_override

    raw_json = os.environ.get("AGENTSWARM_CREDITS_PRICING_JSON", "").strip()
    if raw_json:
        override = json.loads(raw_json)
        if not isinstance(override, dict):
            raise ValueError("AGENTSWARM_CREDITS_PRICING_JSON must be a JSON object")
        for task_class, entry in override.items():
            if not isinstance(task_class, str) or not isinstance(entry, dict):
                raise ValueError("pricing override keys must be task classes with object values")
            merged = table.setdefault(task_class, {})
            for field, value in entry.items():
                merged[str(field)] = float(value)
    return table


def post_cost(task_class: str, *, difficulty: float = 1.0) -> float:
    if difficulty <= 0:
        raise ValueError("difficulty must be positive")
    table = load_pricing_table()
    entry = table.get(task_class)
    if entry is None or "post_cost" not in entry:
        raise ValueError(f"no post_cost pricing for task class {task_class!r}")
    return float(entry["post_cost"]) * difficulty


def reviewer_reward_for(task_class: str = "reviewer.subjective") -> float:
    table = load_pricing_table()
    entry = table.get(task_class)
    if entry is not None and "reviewer_reward" in entry:
        return float(entry["reviewer_reward"])
    fallback = table.get("creative.goal", {})
    if "reviewer_reward" in fallback:
        return float(fallback["reviewer_reward"])
    return 15.0


def verify_mint_for(task_class: str) -> float:
    table = load_pricing_table()
    entry = table.get(task_class)
    if entry is None or "verify_mint" not in entry:
        return 0.0
    return float(entry["verify_mint"])


def public_parameters() -> dict[str, Any]:
    return {
        "enabled": credits_enabled(),
        "initial": initial_credits(),
        "pricing": load_pricing_table(),
    }
