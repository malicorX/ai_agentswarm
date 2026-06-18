"""Run git clone/patch/test inside the Linux sandbox image (git-in-container)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from agentswarm_agents.client import repo_root
from agentswarm_agents.engineering_workspace import goal_branch
from agentswarm_agents.sandbox_executor import (
    DEFAULT_MEMORY,
    ensure_sandbox_test_image,
    run_sandbox_command,
    sandbox_image_ref,
)

MOCK_ENV = "AGENTSWARM_GIT_SANDBOX_MOCK"
GIT_NETWORK_ENV = "AGENTSWARM_SANDBOX_GIT_NETWORK"
AGENTS_SRC_CONTAINER = "/opt/agentswarm/agents/src"

_PATCH_RUNNER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from agentswarm_agents.engineering_workspace import execute_git_engineering_patch
payload = json.load(sys.stdin)
result = execute_git_engineering_patch(
    payload["capsule"],
    goal_id=payload["goal_id"],
    task_id=payload["task_id"],
)
json.dump(result, sys.stdout)
""".strip()

_TEST_RUNNER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from agentswarm_agents.engineering_workspace import run_git_workspace_tests
payload = json.load(sys.stdin)
result = run_git_workspace_tests(payload["capsule"])
json.dump(result, sys.stdout)
""".strip()


def git_sandbox_mock_enabled() -> bool:
    raw = os.environ.get(MOCK_ENV, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def git_sandbox_network() -> str:
    return os.environ.get(GIT_NETWORK_ENV, "bridge").strip() or "bridge"


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _agents_src_mount() -> tuple[str, str]:
    agents_src = Path(repo_root()) / "agents" / "src"
    if not agents_src.is_dir():
        raise FileNotFoundError(f"agents source tree not found: {agents_src}")
    return str(agents_src.resolve()), AGENTS_SRC_CONTAINER


def _rewrite_file_repo_url(repo_url: str) -> tuple[str, list[tuple[str, str, str]]]:
    parsed = urlparse(repo_url)
    if parsed.scheme != "file":
        return repo_url, []
    raw_path = unquote(parsed.path)
    if os.name == "nt" and raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path.lstrip("/")
    repo_path = Path(raw_path)
    mount_parent = str(repo_path.parent.resolve())
    container_repo = str(PurePosixPath("/forge") / repo_path.name)
    return f"file://{container_repo}", [(mount_parent, "/forge", "ro")]


def _prepare_capsule_for_container(capsule: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
    prepared = json.loads(json.dumps(capsule))
    git_info = prepared.get("git")
    if not isinstance(git_info, dict):
        raise ValueError("git capsule requires git section")
    repo_url = str(git_info["repo_url"])
    rewritten, mounts = _rewrite_file_repo_url(repo_url)
    git_info["repo_url"] = rewritten
    return prepared, mounts


def _forge_key_mount(
    forge_credentials: dict[str, Any] | None,
) -> tuple[list[tuple[str, str, str]], list[str], Any]:
    if not isinstance(forge_credentials, dict):
        return [], [], None
    key_pem = forge_credentials.get("private_key_pem") or forge_credentials.get("private_key")
    if forge_credentials.get("type") != "ssh_deploy_key" or not isinstance(key_pem, str) or not key_pem.strip():
        return [], [], None
    handle = tempfile.NamedTemporaryFile(prefix="agentswarm-forge-", suffix=".key", delete=False)
    handle.write((key_pem.strip() + "\n").encode("utf-8"))
    handle.flush()
    handle.close()
    key_path = handle.name
    mounts = [(key_path, "/run/forge/key", "ro")]
    env = [
        "-e",
        (
            "GIT_SSH_COMMAND=ssh -i /run/forge/key -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=accept-new"
        ),
    ]
    return mounts, env, handle


def _run_python_job(
    *,
    verification_spec: dict[str, Any],
    runner: str,
    payload: dict[str, Any],
    capsule: dict[str, Any],
) -> dict[str, Any]:
    if git_sandbox_mock_enabled():
        raise RuntimeError("mock mode should not call _run_python_job")

    prepared_capsule, file_mounts = _prepare_capsule_for_container(capsule)
    payload = {**payload, "capsule": prepared_capsule}
    agents_host, agents_container = _agents_src_mount()
    forge = capsule.get("forge_credentials")
    forge_mounts, forge_env, forge_handle = _forge_key_mount(
        forge if isinstance(forge, dict) else None
    )
    image = ensure_sandbox_test_image(sandbox_image_ref(verification_spec))
    try:
        proc = run_sandbox_command(
            verification_spec=verification_spec,
            image=image,
            command=["python", "-c", runner, agents_container],
            volume_mounts=[
                (agents_host, agents_container, "ro"),
                *file_mounts,
                *forge_mounts,
            ],
            container_workdir="/tmp",
            memory_limit=DEFAULT_MEMORY,
            network=git_sandbox_network(),
            extra_env=forge_env,
            input_text=json.dumps(payload),
            timeout=600,
        )
    finally:
        if forge_handle is not None:
            Path(forge_handle.name).unlink(missing_ok=True)

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        raise RuntimeError(
            f"git sandbox job failed ({proc.returncode}): {(stderr or stdout)[-800:]}"
        )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"git sandbox job returned invalid JSON: {stdout[:400]}") from exc


def _mock_git_patch_result(
    *,
    capsule: dict[str, Any],
    goal_id: str,
    task_id: str,
) -> dict[str, Any]:
    git_info = capsule.get("git") or {}
    branch = goal_branch(goal_id)
    commit_sha = "0" * 40
    return {
        "applied": True,
        "file": str((capsule.get("patch") or {}).get("file", "README.md")),
        "git_artifact": {
            "repo_url": str(git_info.get("repo_url", "")),
            "branch": branch,
            "commit_sha": commit_sha,
            "forge_type": str(git_info.get("forge_type", "git")),
        },
        "workspace_ref": commit_sha,
        "sandbox": True,
        "git_in_container": True,
        "mock": True,
    }


def execute_git_engineering_patch_sandbox(
    capsule: dict[str, Any],
    *,
    goal_id: str,
    task_id: str,
    verification_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Clone/patch/push via git inside the sandbox image; host only orchestrates Docker."""
    spec = dict(verification_spec or {})
    if task_id and not spec.get("sandbox_run_id"):
        spec["sandbox_run_id"] = task_id
    if git_sandbox_mock_enabled():
        return _mock_git_patch_result(capsule=capsule, goal_id=goal_id, task_id=task_id)

    result = _run_python_job(
        verification_spec=spec,
        runner=_PATCH_RUNNER,
        payload={"capsule": capsule, "goal_id": goal_id, "task_id": task_id},
        capsule=capsule,
    )
    result["sandbox"] = True
    result["git_in_container"] = True
    return result


def run_git_workspace_tests_sandbox(
    capsule: dict[str, Any],
    *,
    verification_spec: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Clone workspace_ref and run pytest inside the sandbox image."""
    spec = dict(verification_spec or {})
    if task_id and not spec.get("sandbox_run_id"):
        spec["sandbox_run_id"] = task_id
    if git_sandbox_mock_enabled():
        workspace_ref = capsule.get("workspace_ref") or "0" * 40
        stdout = f"mock git sandbox test ok ref={workspace_ref}\n"
        return {
            "passed": True,
            "returncode": 0,
            "workspace_ref": workspace_ref,
            "sandbox": True,
            "git_in_container": True,
            "mock": True,
            "stdout": stdout,
            "stderr": "",
            "run_artifact": {
                "passed": True,
                "exit_code": 0,
                "stdout_digest": _digest_text(stdout),
                "stderr_digest": _digest_text(""),
            },
        }

    result = _run_python_job(
        verification_spec=spec,
        runner=_TEST_RUNNER,
        payload={"capsule": capsule},
        capsule=capsule,
    )
    result["sandbox"] = True
    result["git_in_container"] = True
    return result
