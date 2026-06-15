from __future__ import annotations

import os

from agentswarm_platform import credibility

CROSS_PROJECT_HAIRCUT = float(
    os.environ.get("AGENTSWARM_CRED_CROSS_PROJECT_HAIRCUT", "0.5")
)


def compute_imported_score(
    source_score: float,
    *,
    haircut: float = CROSS_PROJECT_HAIRCUT,
    initial_score: float | None = None,
) -> float:
    """Transfer earned credibility from another project with a haircut."""
    base = credibility.INITIAL_SCORE if initial_score is None else initial_score
    earned = max(0.0, source_score - base)
    return base + earned * haircut


def transfer_rules() -> dict[str, float | str | bool]:
    return {
        "haircut_rate": CROSS_PROJECT_HAIRCUT,
        "initial_score": credibility.INITIAL_SCORE,
        "formula": "initial + max(0, source - initial) * haircut_rate",
        "one_import_per_source_target_capability": True,
    }
