from __future__ import annotations

from unittest.mock import patch

from agentswarm_agents.sandbox_executor import _docker_run_cmd


def test_docker_run_cmd_includes_security_and_name(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSWARM_SANDBOX_HARDEN", "1")
    monkeypatch.setenv("AGENTSWARM_SANDBOX_SECCOMP_PROFILE", "")
    with patch("agentswarm_agents.sandbox_executor.cleanup_sandbox_container"):
        cmd = _docker_run_cmd(
            verification_spec={"sandbox_run_id": "task_deadbeef"},
            image="agentswarm/sandbox-pytest:3.12",
            host_path="/tmp/fixture",
            container_work="/work",
            memory_limit="512m",
            network="none",
            command=["python", "-m", "pytest", "tests", "-q"],
        )
    assert "--name" in cmd
    assert "agentswarm-sandbox-task_deadbeef" in cmd
    assert "--cap-drop=ALL" in cmd
