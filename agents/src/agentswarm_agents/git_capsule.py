from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return proc.stdout.strip()


def _configure_identity(repo_dir: Path, *, env: dict[str, str] | None = None) -> None:
    _run_git(["config", "user.email", "agentswarm@local"], cwd=repo_dir, env=env)
    _run_git(["config", "user.name", "AgentSwarm"], cwd=repo_dir, env=env)


@contextmanager
def forge_git_env(credentials: dict[str, Any] | None) -> Iterator[dict[str, str]]:
    """Temporarily configure GIT_SSH_COMMAND for a scoped deploy key."""
    if not credentials:
        yield {}
        return
    key_pem = credentials.get("private_key_pem") or credentials.get("private_key")
    if credentials.get("type") != "ssh_deploy_key" or not isinstance(key_pem, str) or not key_pem.strip():
        yield {}
        return
    fd, key_name = tempfile.mkstemp(prefix="agentswarm-forge-", suffix=".key")
    os.close(fd)
    key_path = Path(key_name)
    try:
        key_path.write_text(key_pem.strip() + "\n", encoding="utf-8")
        if os.name != "nt":
            key_path.chmod(0o600)
        ssh_cmd = (
            f'ssh -i "{key_path}" -o IdentitiesOnly=yes '
            "-o StrictHostKeyChecking=accept-new"
        )
        merged = os.environ.copy()
        merged["GIT_SSH_COMMAND"] = ssh_cmd
        yield merged
    finally:
        key_path.unlink(missing_ok=True)


def clone_repo(
    repo_url: str,
    target_dir: Path,
    *,
    default_branch: str,
    env: dict[str, str] | None = None,
) -> None:
    proc = subprocess.run(
        ["git", "clone", repo_url, str(target_dir)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {proc.stderr.strip()}")
    _configure_identity(target_dir, env=env)
    _run_git(["checkout", default_branch], cwd=target_dir, env=env)


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
    env: dict[str, str] | None = None,
    allowed_branch_prefix: str | None = None,
) -> str:
    if allowed_branch_prefix and not branch.startswith(allowed_branch_prefix):
        raise ValueError(
            f"branch {branch!r} is outside forge scope {allowed_branch_prefix!r}"
        )
    _run_git(["checkout", "-B", branch], cwd=repo_dir, env=env)
    _run_git(["add", "-A"], cwd=repo_dir, env=env)
    _run_git(["commit", "-m", message], cwd=repo_dir, env=env)
    commit_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_dir, env=env)
    push_args = ["push"]
    if branch.startswith("agentswarm/"):
        push_args.append("--force")
    push_args.extend([remote_url, f"HEAD:{branch}"])
    _run_git(push_args, cwd=repo_dir, env=env)
    return commit_sha


def execute_git_patch_capsule(capsule: dict[str, Any]) -> dict[str, Any]:
    """Apply a bounded text patch via local git (ADR 0009 — forge-agnostic v1)."""
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
