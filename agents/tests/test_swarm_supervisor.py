from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from agentswarm_agents.swarm_supervisor import (
    DEFAULT_WORKERS,
    WorkerSpec,
    _worker_command,
    run_supervisor,
)


def test_worker_command_uses_module() -> None:
    spec = WorkerSpec("planner", "agentswarm_agents.workers.planner")
    cmd = _worker_command(spec, poll_interval=3.0)
    assert cmd[0] == sys.executable
    assert "agentswarm_agents.workers.planner" in cmd
    assert cmd[-1] == "3.0"


def test_run_supervisor_respawns_exited_worker() -> None:
    spawn_count = 0

    def fake_spawn(_cmd: list[str]) -> MagicMock:
        nonlocal spawn_count
        spawn_count += 1
        proc = MagicMock()
        proc.pid = spawn_count
        proc.poll.return_value = 1 if spawn_count == 1 else None
        proc.wait.return_value = 0
        return proc

    workers = (WorkerSpec("planner", "agentswarm_agents.workers.planner"),)
    calls = {"n": 0}

    def stop_after_respawn(_sec: float) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt

    with patch("agentswarm_agents.swarm_supervisor.ensure_scan_task"):
        with patch("agentswarm_agents.swarm_supervisor.signal.signal"):
            with patch("agentswarm_agents.swarm_supervisor.time.sleep", side_effect=stop_after_respawn):
                try:
                    run_supervisor(
                        workers=workers,
                        scan_interval_sec=0,
                        spawn=fake_spawn,
                    )
                except KeyboardInterrupt:
                    pass

    assert spawn_count >= 2
