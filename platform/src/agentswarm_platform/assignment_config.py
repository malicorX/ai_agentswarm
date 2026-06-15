from __future__ import annotations

import os
from typing import Literal

AssignmentMode = Literal["pull", "dispatch"]


def assignment_mode() -> AssignmentMode:
    raw = os.environ.get("AGENTSWARM_ASSIGNMENT_MODE", "pull").strip().lower()
    if raw not in ("pull", "dispatch"):
        raise ValueError("AGENTSWARM_ASSIGNMENT_MODE must be 'pull' or 'dispatch'")
    return raw  # type: ignore[return-value]


def dispatch_enabled() -> bool:
    return assignment_mode() == "dispatch"
