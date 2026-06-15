from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Callable

from agentswarm_platform.assignment_signing import verify_assignment


def default_worker_image() -> str:
    return os.environ.get("AGENTSWARM_WORKER_IMAGE", "agentswarm-worker:dev")


def docker_available(docker_bin: str = "docker") -> bool:
    if shutil.which(docker_bin) is None:
        return False
    try:
        proc = subprocess.run(
            [docker_bin, "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def assignment_signature_payload(assignment: dict[str, Any], agent_id: str) -> dict[str, str]:
    return {
        "lease_id": str(assignment["lease_id"]),
        "agent_id": agent_id,
        "task_id": str(assignment["task_id"]),
        "expires_at": str(assignment["expires_at"]),
    }


def verify_assignment_signature(assignment: dict[str, Any], agent_id: str) -> None:
    payload = assignment_signature_payload(assignment, agent_id)
    signature = assignment.get("assignment_signature", "")
    if not signature or not verify_assignment(payload, signature):
        raise ValueError("invalid or missing assignment signature")


def build_worker_input(assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_type": assignment.get("task_type", ""),
        "capsule": assignment.get("capsule") or {},
    }


def run_capsule_in_docker(
    assignment: dict[str, Any],
    *,
    agent_id: str,
    image: str | None = None,
    timeout_sec: float = 120.0,
    docker_bin: str = "docker",
    network_mode: str = "none",
) -> dict[str, Any]:
    verify_assignment_signature(assignment, agent_id)
    resolved_image = image or default_worker_image()
    payload = json.dumps(build_worker_input(assignment), separators=(",", ":"))
    proc = subprocess.run(
        [
            docker_bin,
            "run",
            "--rm",
            "-i",
            "--network",
            network_mode,
            resolved_image,
        ],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"worker container failed (exit {proc.returncode}): {stderr or 'no stderr'}"
        )
    stdout = proc.stdout.decode("utf-8", errors="replace").strip()
    if not stdout:
        raise RuntimeError("worker container returned empty stdout")
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"worker container returned invalid JSON: {stdout[:200]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("worker container result must be a JSON object")
    return result


def docker_capsule_executor(
    agent_id: str,
    *,
    image: str | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _executor(assignment: dict[str, Any]) -> dict[str, Any]:
        return run_capsule_in_docker(assignment, agent_id=agent_id, image=image)

    return _executor
