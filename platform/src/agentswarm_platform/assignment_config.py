from __future__ import annotations

import os
from typing import Literal

AssignmentMode = Literal["pull", "dispatch"]

# Migration phase 3 (ROADMAP_CHANGES): production uses dispatch; pull is maintainer/dev only.
PRODUCTION_ASSIGNMENT_MODE: AssignmentMode = "dispatch"
LOCAL_DEV_ASSIGNMENT_MODE: AssignmentMode = "pull"
VOLUNTEER_REQUIRED_MODE: AssignmentMode = "dispatch"


def assignment_mode() -> AssignmentMode:
    raw = os.environ.get("AGENTSWARM_ASSIGNMENT_MODE", "pull").strip().lower()
    if raw not in ("pull", "dispatch"):
        raise ValueError("AGENTSWARM_ASSIGNMENT_MODE must be 'pull' or 'dispatch'")
    return raw  # type: ignore[return-value]


def dispatch_enabled() -> bool:
    return assignment_mode() == "dispatch"


def public_parameters() -> dict[str, str | bool]:
    """Published on GET /platform/config for client migration guidance."""
    mode = assignment_mode()
    return {
        "mode": mode,
        "volunteer_requires": VOLUNTEER_REQUIRED_MODE,
        "production_default": PRODUCTION_ASSIGNMENT_MODE,
        "local_dev_default": LOCAL_DEV_ASSIGNMENT_MODE,
        "pull_for_maintainer_scripts": True,
    }
