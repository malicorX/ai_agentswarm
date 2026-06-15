from __future__ import annotations

import time

import pytest

from agentswarm_platform.assignment_wait import (
    clamp_wait_sec,
    wait_for_pending_assignment,
)


def test_clamp_wait_sec_rejects_above_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_LONG_POLL_MAX_SEC", "10")
    with pytest.raises(ValueError, match="maximum"):
        clamp_wait_sec(11)


def test_wait_for_pending_assignment_returns_when_late(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_LONG_POLL_INTERVAL_SEC", "0.01")
    calls = {"count": 0}

    def fetch(agent_id: str) -> dict[str, str] | None:
        calls["count"] += 1
        if calls["count"] >= 3:
            return {"agent_id": agent_id, "task_id": "task-1"}
        return None

    started = time.monotonic()
    result = wait_for_pending_assignment(fetch, "agent-1", 1.0)
    elapsed = time.monotonic() - started
    assert result == {"agent_id": "agent-1", "task_id": "task-1"}
    assert calls["count"] >= 3
    assert elapsed >= 0.02
