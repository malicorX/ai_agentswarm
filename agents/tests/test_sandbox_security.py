from __future__ import annotations

from agentswarm_agents.sandbox_security import (
    docker_security_args,
    sandbox_container_name,
    sandbox_hardening_enabled,
)


def test_sandbox_hardening_enabled_default() -> None:
    assert sandbox_hardening_enabled() is True


def test_docker_security_args_include_hardening(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSWARM_SANDBOX_HARDEN", "1")
    monkeypatch.delenv("AGENTSWARM_SANDBOX_SECCOMP_PROFILE", raising=False)
    args = docker_security_args()
    assert "--security-opt=no-new-privileges" in args
    assert "--cap-drop=ALL" in args
    assert any(a.startswith("--tmpfs=") for a in args)


def test_docker_security_args_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSWARM_SANDBOX_HARDEN", "0")
    assert docker_security_args() == []


def test_sandbox_container_name_sanitizes() -> None:
    assert sandbox_container_name("task_abc123").startswith("agentswarm-sandbox-")
    assert sandbox_container_name("task/with spaces!").startswith("agentswarm-sandbox-")
