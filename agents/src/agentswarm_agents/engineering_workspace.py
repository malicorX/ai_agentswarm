"""Git workspace helpers for distributed engineering goals (D0)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agentswarm_agents.engineering_lab import (
    fixture_dir,
    get_fixture_spec,
    mock_body_for_fixture,
    reset_fixture,
)
from agentswarm_agents.client import repo_root
from agentswarm_agents.git_capsule import (
    _configure_identity,
    _run_git,
    apply_text_patch,
    clone_repo,
    commit_and_push,
    forge_git_env,
)

def goal_branch(goal_id: str) -> str:
    if goal_id.startswith("goal-"):
        return f"agentswarm/{goal_id}"
    return f"agentswarm/goal-{goal_id}"


def workspace_mode(verification_spec: dict[str, Any] | None) -> str:
    if not verification_spec:
        return "local_fixture"
    return str(verification_spec.get("workspace_mode", "local_fixture"))


def git_workspace_from_url(
    repo_url: str,
    *,
    default_branch: str = "main",
    forge_type: str = "git",
) -> dict[str, str]:
    cleaned = repo_url.strip()
    if not cleaned:
        raise ValueError("workspace repo_url must not be empty")
    return {
        "mode": "git",
        "repo_url": cleaned,
        "default_branch": default_branch,
        "forge_type": forge_type,
    }


def resolve_engineering_git_workspace(
    *,
    fixture: str = "primes",
    workspace_repo_url: str | None = None,
    workspace_root: Path | None = None,
) -> dict[str, str]:
    """Use a shared remote bare repo when configured, else seed file:// under repo root."""
    env_url = os.environ.get("AGENTSWARM_GIT_REPO_URL", "").strip()
    resolved_url = (workspace_repo_url or env_url or "").strip()
    if resolved_url:
        return git_workspace_from_url(resolved_url)
    root = workspace_root or Path(repo_root()) / ".agentswarm-git-workspaces"
    return init_local_git_workspace(root, fixture=fixture)


def init_local_git_workspace(
    base_dir: Path,
    *,
    fixture: str = "primes",
) -> dict[str, str]:
    """Create a file:// bare repo seeded with an engineering-lab fixture stub."""
    base_dir.mkdir(parents=True, exist_ok=True)
    bare = base_dir / f"{fixture}.git"
    work = base_dir / f"{fixture}-seed"
    if bare.exists():
        return {
            "mode": "git",
            "repo_url": bare.as_uri(),
            "default_branch": "main",
            "forge_type": "git",
        }
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    _run_git(["init", "-b", "main"], cwd=work)
    _configure_identity(work)
    spec = get_fixture_spec(fixture)
    target = work / spec.patch_file
    reset_fixture(fixture)
    source = fixture_dir(fixture) / spec.patch_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    tests_src = fixture_dir(fixture) / "tests"
    if tests_src.is_dir():
        shutil.copytree(tests_src, work / "tests")
    _run_git(["add", "-A"], cwd=work)
    _run_git(["commit", "-m", "seed engineering fixture"], cwd=work)
    subprocess.run(["git", "clone", "--bare", str(work), str(bare)], check=True)
    shutil.rmtree(work, ignore_errors=True)
    return {
        "mode": "git",
        "repo_url": bare.as_uri(),
        "default_branch": "main",
        "forge_type": "git",
    }


def execute_git_engineering_patch(
    capsule: dict[str, Any],
    *,
    goal_id: str,
    task_id: str,
    insert_body: str | None = None,
) -> dict[str, Any]:
    """Patch engineering source in a goal-scoped git branch."""
    git_info = capsule.get("git")
    patch = capsule.get("patch")
    if not isinstance(git_info, dict) or not isinstance(patch, dict):
        raise ValueError("git engineering capsule requires git and patch sections")
    repo_url = str(git_info["repo_url"])
    default_branch = str(git_info.get("default_branch", "main"))
    branch = goal_branch(goal_id)
    forge = capsule.get("forge_credentials")
    if not isinstance(forge, dict):
        forge = None
    workdir = Path(tempfile.mkdtemp(prefix="agentswarm-eng-git-"))
    try:
        with forge_git_env(forge) as git_env:
            clone_repo(repo_url, workdir, default_branch=default_branch, env=git_env or None)
            patch_body = dict(patch)
            if insert_body is None and isinstance(capsule.get("lab"), dict):
                fixture = str(capsule["lab"].get("fixture", "primes"))
                insert_body = mock_body_for_fixture(fixture)
            if insert_body is not None:
                patch_body["insert"] = insert_body
            rel_path = apply_text_patch(workdir, patch_body)
            branch_prefix = str(forge.get("branch_prefix")) if forge else None
            commit_sha = commit_and_push(
                workdir,
                branch=branch,
                remote_url=repo_url,
                message=f"agentswarm engineering goal {goal_id}",
                env=git_env or None,
                allowed_branch_prefix=branch_prefix,
            )
        git_artifact = {
            "repo_url": repo_url,
            "branch": branch,
            "commit_sha": commit_sha,
            "forge_type": str(git_info.get("forge_type", "git")),
        }
        return {
            "applied": True,
            "file": rel_path,
            "git_artifact": git_artifact,
            "workspace_ref": commit_sha,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def clone_at_workspace_ref(
    repo_url: str,
    commit_sha: str,
    *,
    default_branch: str = "main",
    forge_credentials: dict[str, Any] | None = None,
) -> Path:
    """Clone and checkout a specific commit into a temp directory."""
    workdir = Path(tempfile.mkdtemp(prefix="agentswarm-clone-"))
    with forge_git_env(forge_credentials) as git_env:
        clone_repo(repo_url, workdir, default_branch=default_branch, env=git_env or None)
        _run_git(["checkout", commit_sha], cwd=workdir, env=git_env or None)
    return workdir


def run_pytest_in_dir(repo_dir: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def run_git_workspace_tests(capsule: dict[str, Any]) -> dict[str, Any]:
    git_info = capsule.get("git")
    workspace_ref = capsule.get("workspace_ref") or capsule.get("parent_git_artifact", {}).get(
        "commit_sha"
    )
    if not isinstance(git_info, dict) or not workspace_ref:
        raise ValueError("git tester requires git info and workspace_ref")
    repo_url = str(git_info["repo_url"])
    default_branch = str(git_info.get("default_branch", "main"))
    forge = capsule.get("forge_credentials")
    if not isinstance(forge, dict):
        forge = None
    workdir = clone_at_workspace_ref(
        repo_url,
        str(workspace_ref),
        default_branch=default_branch,
        forge_credentials=forge,
    )
    try:
        result = run_pytest_in_dir(workdir)
        result["workspace_ref"] = workspace_ref
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
