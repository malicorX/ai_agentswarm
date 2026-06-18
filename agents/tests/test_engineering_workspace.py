from __future__ import annotations

from pathlib import Path

from agentswarm_agents.engineering_workspace import (
    execute_git_engineering_patch,
    git_workspace_from_url,
    init_local_git_workspace,
    resolve_engineering_git_workspace,
    run_git_workspace_tests,
)


def test_git_engineering_patch_and_test(tmp_path: Path) -> None:
    workspace = init_local_git_workspace(tmp_path, fixture="primes")
    capsule = {
        "goal_id": "goal-test-git",
        "git": workspace,
        "lab": {"fixture": "primes"},
        "patch": {
            "file": "primes.py",
            "marker": "<!-- agentswarm:implement -->",
        },
    }
    patch_result = execute_git_engineering_patch(
        capsule,
        goal_id="goal-test-git",
        task_id="task-1",
    )
    assert patch_result["applied"] is True
    assert patch_result.get("workspace_ref")
    assert patch_result.get("git_artifact")

    tester_capsule = {
        "git": workspace,
        "workspace_ref": patch_result["workspace_ref"],
    }
    test_result = run_git_workspace_tests(tester_capsule)
    assert test_result["passed"] is True


def test_git_workspace_from_url() -> None:
    workspace = git_workspace_from_url("root@theebie.de:/var/lib/agentswarm/git-workspaces/primes.git")
    assert workspace["mode"] == "git"
    assert workspace["repo_url"].startswith("root@theebie.de:")


def test_resolve_engineering_git_workspace_uses_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTSWARM_GIT_REPO_URL", "root@host:/repo.git")
    workspace = resolve_engineering_git_workspace(fixture="primes", workspace_root=tmp_path)
    assert workspace["repo_url"] == "root@host:/repo.git"


def test_resolve_engineering_git_workspace_local_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGENTSWARM_GIT_REPO_URL", raising=False)
    workspace = resolve_engineering_git_workspace(fixture="primes", workspace_root=tmp_path)
    assert workspace["repo_url"].startswith("file:")
