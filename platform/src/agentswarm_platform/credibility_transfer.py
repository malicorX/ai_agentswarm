from __future__ import annotations

import os

from agentswarm_platform.credibility import INITIAL_SCORE

CROSS_PROJECT_HAIRCUT = float(
    os.environ.get("AGENTSWARM_CRED_CROSS_PROJECT_HAIRCUT", "0.5")
)


def compute_imported_score(
    source_score: float,
    *,
    haircut: float = CROSS_PROJECT_HAIRCUT,
    initial_score: float = INITIAL_SCORE,
) -> float:
    """Transfer earned credibility from another project with a haircut."""
    earned = max(0.0, source_score - initial_score)
    return initial_score + earned * haircut


def transfer_rules() -> dict[str, float | str | bool]:
    return {
        "haircut_rate": CROSS_PROJECT_HAIRCUT,
        "initial_score": INITIAL_SCORE,
        "formula": "initial + max(0, source - initial) * haircut_rate",
        "one_import_per_source_target_capability": True,
    }
