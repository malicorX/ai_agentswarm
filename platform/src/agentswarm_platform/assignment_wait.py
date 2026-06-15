"""Server-side long-poll for dispatch assignment leases."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any


def assignment_long_poll_max_sec() -> float:
    return float(os.environ.get("AGENTSWARM_ASSIGNMENT_LONG_POLL_MAX_SEC", "60"))


def assignment_long_poll_interval_sec() -> float:
    return float(os.environ.get("AGENTSWARM_ASSIGNMENT_LONG_POLL_INTERVAL_SEC", "0.25"))


def assignment_lease_ttl_minutes() -> int:
    raw = os.environ.get("AGENTSWARM_ASSIGNMENT_LEASE_TTL_MINUTES", "60").strip()
    return max(1, int(raw))


def pool_need_max_age_hours() -> float:
    """Max hours a pending pool need may wait before automatic cancellation (0 = disabled)."""
    raw = os.environ.get("AGENTSWARM_POOL_NEED_MAX_AGE_HOURS", "0").strip()
    return max(0.0, float(raw))


def dispatch_public_parameters() -> dict[str, float | int]:
    return {
        "long_poll_max_sec": assignment_long_poll_max_sec(),
        "long_poll_interval_sec": assignment_long_poll_interval_sec(),
        "lease_ttl_minutes": assignment_lease_ttl_minutes(),
        "pool_need_max_age_hours": pool_need_max_age_hours(),
    }


def clamp_wait_sec(wait_sec: float) -> float:
    if wait_sec < 0:
        raise ValueError("wait_sec must be non-negative")
    max_sec = assignment_long_poll_max_sec()
    if wait_sec > max_sec:
        raise ValueError(f"wait_sec exceeds maximum {max_sec}")
    return wait_sec


def wait_for_pending_assignment(
    fetch: Callable[[str], dict[str, Any] | None],
    agent_id: str,
    wait_sec: float,
    *,
    poll_interval: float | None = None,
) -> dict[str, Any] | None:
    """Return a pending assignment immediately or after waiting up to wait_sec."""
    if wait_sec <= 0:
        return fetch(agent_id)

    interval = poll_interval if poll_interval is not None else assignment_long_poll_interval_sec()
    deadline = time.monotonic() + wait_sec
    while True:
        assignment = fetch(agent_id)
        if assignment is not None:
            return assignment
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(interval, remaining))
