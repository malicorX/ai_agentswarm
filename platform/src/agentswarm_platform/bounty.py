from __future__ import annotations

from typing import Any


def parse_bounty_bonus(payload: dict[str, Any]) -> float:
    """Extra credibility minted on verified acceptance (ROADMAP §7.3)."""
    bounty = payload.get("bounty")
    if bounty is None:
        return 0.0
    if isinstance(bounty, (int, float)):
        bonus = float(bounty)
    elif isinstance(bounty, dict):
        bonus = float(
            bounty.get(
                "credibility_bonus",
                bounty.get("bonus", bounty.get("amount", 0)),
            )
        )
    else:
        return 0.0
    if bonus < 0:
        raise ValueError("bounty bonus must be non-negative")
    return bonus
