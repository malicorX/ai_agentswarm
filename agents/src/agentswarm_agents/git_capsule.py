from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _run_git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return proc.stdout.strip()


def _configure_identity(repo_dir: Path) -> None:
    _run_git(["config", "user.email", "agentswarm@local"], cwd=repo_dir)
    _run_git(["config", "user.name", "AgentSwarm"], cwd=repo_dir)


def clone_repo(repo_url: str, target_dir: Path, *, default_branch: str) -> None:
    proc = subprocess.run(
        ["git", "clone", repo_url, str(target_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {proc.stderr.strip()}")
    _configure_identity(target_dir)
    _run_git(["checkout", default_branch], cwd=target_dir)


def apply_text_patch(repo_dir: Path, patch: dict[str, Any]) -> str:
    rel_path = str(patch["file"])
    marker = str(patch.get("marker", "<!-- agentswarm -->"))
    insert = str(patch.get("insert", ""))
    target = repo_dir / rel_path
    if not target.exists():
        raise FileNotFoundError(f"patch target not found: {rel_path}")
    content = target.read_text(encoding="utf-8")
    if marker in content:
        new_content = content.replace(marker, f"{marker}\n{insert}")
    else:
        new_content = content + f"\n{marker}\n{insert}\n"
    target.write_text(new_content, encoding="utf-8")
    return rel_path


def commit_and_push(
    repo_dir: Path,
    *,
    branch: str,
    remote_url: str,
    message: str,
) -> str:
    _run_git(["checkout", "-B", branch], cwd=repo_dir)
    _run_git(["add", "-A"], cwd=repo_dir)
    _run_git(["commit", "-m", message], cwd=repo_dir)
    commit_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_dir)
    _run_git(["push", remote_url, f"HEAD:{branch}"], cwd=repo_dir)
    return commit_sha


def execute_git_patch_capsule(capsule: dict[str, Any]) -> dict[str, Any]:
    git_info = capsule.get("git")
    patch = capsule.get("patch")
    if not isinstance(git_info, dict):
        raise ValueError("capsule.git is required for git-backed codewriter tasks")
    if not isinstance(patch, dict):
        raise ValueError("capsule.patch is required for git-backed codewriter tasks")
    task_id = str(capsule.get("task_id") or "task")
    repo_url = str(git_info["repo_url"])
    default_branch = str(git_info.get("default_branch", "main"))
    forge_type = str(git_info.get("forge_type", "git"))
    branch = f"agentswarm/{task_id}"

    workdir = Path(tempfile.mkdtemp(prefix="agentswarm-git-"))
    try:
        clone_repo(repo_url, workdir, default_branch=default_branch)
        rel_path = apply_text_patch(workdir, patch)
        commit_sha = commit_and_push(
            workdir,
            branch=branch,
            remote_url=repo_url,
            message=f"agentswarm patch for {task_id}",
        )
        return {
            "applied": True,
            "file": rel_path,
            "git_artifact": {
                "repo_url": repo_url,
                "branch": branch,
                "commit_sha": commit_sha,
                "forge_type": forge_type,
            },
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
