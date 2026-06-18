from __future__ import annotations

import pytest

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.git_sandbox_executor import (
    execute_git_engineering_patch_sandbox,
    git_sandbox_mock_enabled,
    run_git_workspace_tests_sandbox,
)


def test_git_sandbox_mock_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_GIT_SANDBOX_MOCK", "1")
    assert git_sandbox_mock_enabled()
    result = execute_git_engineering_patch_sandbox(
        {
            "git": {"repo_url": "file:///tmp/repo.git", "default_branch": "main"},
            "patch": {"file": "primes.py", "marker": "<!-- agentswarm:implement -->"},
            "lab": {"fixture": "primes"},
        },
        goal_id="goal-git-sandbox",
        task_id="task-git-patch",
    )
    assert result["applied"] is True
    assert result["git_in_container"] is True
    assert result["workspace_ref"]


def test_git_sandbox_mock_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_GIT_SANDBOX_MOCK", "1")
    result = run_git_workspace_tests_sandbox(
        {
            "git": {"repo_url": "file:///tmp/repo.git", "default_branch": "main"},
            "workspace_ref": "a" * 40,
            "verification_spec": {"git_in_container": True},
        },
        task_id="task-git-test",
    )
    assert result["passed"] is True
    assert result["git_in_container"] is True


def test_capsule_executor_routes_git_in_container_codewriter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_GIT_SANDBOX_MOCK", "1")
    result = execute_capsule(
        {
            "task_type": "codewriter.patch",
            "task_id": "task-cw-git",
            "goal_id": "goal-cw-git",
            "capsule": {
                "goal_id": "goal-cw-git",
                "git": {"repo_url": "file:///tmp/repo.git", "default_branch": "main"},
                "patch": {"file": "primes.py"},
                "lab": {"fixture": "primes"},
                "sandbox_git": True,
            },
        }
    )
    assert result["git_in_container"] is True


def test_capsule_executor_routes_git_in_container_tester(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_GIT_SANDBOX_MOCK", "1")
    result = execute_capsule(
        {
            "task_type": "tester.run",
            "task_id": "task-t-git",
            "capsule": {
                "git": {"repo_url": "file:///tmp/repo.git", "default_branch": "main"},
                "workspace_ref": "b" * 40,
                "verification_spec": {"git_in_container": True},
            },
        }
    )
    assert result["passed"] is True
    assert result["git_in_container"] is True
