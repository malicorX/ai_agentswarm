from __future__ import annotations

import subprocess

import pytest

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.windows_sandbox_executor import (
    run_compile_windows_vm,
    run_fixture_tests_windows_vm,
    windows_sandbox_mock_enabled,
)


def test_windows_sandbox_mock_compile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_WINDOWS_SANDBOX_MOCK", "1")
    assert windows_sandbox_mock_enabled()
    result = run_compile_windows_vm(
        {"fixture": "primes", "workspace_mode": "windows", "sandbox_run_id": "task-mock"}
    )
    assert result["passed"] is True
    assert result["windows_vm"] is True
    assert result["mock"] is True
    assert result["build_artifact"]["passed"] is True


def test_windows_sandbox_mock_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_WINDOWS_SANDBOX_MOCK", "1")
    result = run_fixture_tests_windows_vm(
        {"fixture": "primes", "workspace_mode": "windows", "sandbox_run_id": "task-mock"}
    )
    assert result["passed"] is True
    assert result["run_artifact"]["passed"] is True


def test_capsule_executor_routes_windows_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_WINDOWS_SANDBOX_MOCK", "1")
    result = execute_capsule(
        {
            "task_type": "builder.compile",
            "task_id": "task-win-build",
            "verification_spec": {
                "fixture": "primes",
                "workspace_mode": "windows",
            },
        }
    )
    assert result["windows_vm"] is True
    assert result["passed"] is True


def test_windows_sandbox_mock_winhello_builds_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_WINDOWS_SANDBOX_MOCK", "1")
    monkeypatch.setenv("AGENTSWARM_WINDOWS_SNAPSHOT_NAME", "clean")
    monkeypatch.setenv("AGENTSWARM_WINDOWS_NETWORK_ISOLATED", "1")
    result = run_compile_windows_vm(
        {"fixture": "winhello", "workspace_mode": "windows", "sandbox_run_id": "task-winhello"}
    )
    assert result["passed"] is True
    assert result["build_artifact"]["exe_built"] is True
    assert result["snapshot_reverted"] is True
    assert result["network_isolated"] is True


def test_vm_hardening_restores_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_WINDOWS_SANDBOX_MOCK", raising=False)
    monkeypatch.setenv("AGENTSWARM_WINDOWS_NETWORK_ISOLATED", "1")
    calls: list[str] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        joined = " ".join(cmd)
        calls.append(joined)
        stdout = "True" if "Hyper-V" in joined else "Running"
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    monkeypatch.setattr(
        "agentswarm_agents.windows_sandbox_executor.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "agentswarm_agents.windows_sandbox_executor.hyperv_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "agentswarm_agents.windows_sandbox_executor._vm_state",
        lambda _name: "Running",
    )
    monkeypatch.setattr(
        "agentswarm_agents.windows_sandbox_executor._sync_fixture_to_guest",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "agentswarm_agents.windows_sandbox_executor._invoke_guest_script",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "ok", ""),
    )

    from agentswarm_agents.windows_sandbox_executor import _vm_hardening_session

    with _vm_hardening_session("agentswarm-sandbox-win") as meta:
        assert meta["network_isolated"] is True
    assert any("Disable-VMNetworkAdapter" in call for call in calls)
    assert any("Enable-VMNetworkAdapter" in call for call in calls)


def test_capsule_executor_routes_windows_tester(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_WINDOWS_SANDBOX_MOCK", "1")
    result = execute_capsule(
        {
            "task_type": "tester.run",
            "task_id": "task-win-test",
            "capsule": {
                "verification_spec": {
                    "fixture": "primes",
                    "workspace_mode": "windows",
                }
            },
        }
    )
    assert result["windows_vm"] is True
    assert result["passed"] is True
