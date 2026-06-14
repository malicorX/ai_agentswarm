from __future__ import annotations

from typing import Any

from agentswarm_platform.replication import result_fingerprint


def parse_canary_expectation(payload: dict[str, Any]) -> dict[str, Any] | None:
    canary = payload.get("canary")
    if not canary:
        return None
    expected = canary.get("expected")
    if not isinstance(expected, dict):
        raise ValueError("canary.expected must be an object")
    return expected


def canary_passes(task_type: str, expected: dict[str, Any], result: dict[str, Any]) -> bool:
    return result_fingerprint(task_type, expected) == result_fingerprint(task_type, result)
