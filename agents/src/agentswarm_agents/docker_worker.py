"""Run engineering capsules inside an ephemeral OCI worker container."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from agentswarm_agents.llama_io import parse_worker_container_failure
from agentswarm_agents.model_store import worker_image_for_model
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
        "verification_spec": assignment.get("verification_spec"),
        "goal_id": assignment.get("goal_id"),
    }


def _docker_run_args(
    *,
    image: str,
    model_path: Path | None,
    model_entry: dict[str, Any] | None,
    docker_bin: str,
    network_mode: str,
) -> list[str]:
    args = [
        docker_bin,
        "run",
        "--rm",
        "-i",
        "--network",
        network_mode,
    ]
    if model_path is not None and model_path.is_file():
        mount_target = "/models/weights"
        args.extend(["-v", f"{model_path.resolve()}:{mount_target}/model.gguf:ro"])
        args.extend(["-e", f"AGENTSWARM_MODEL_PATH={mount_target}/model.gguf"])
        if model_entry and model_entry.get("id", "").startswith("docker/"):
            args.extend(["-e", "AGENTSWARM_ENGINEERING_LLM=1"])
            if not os.environ.get("AGENTSWARM_LLAMA_LOG"):
                args.extend(["-e", "LLAMA_LOG_VERBOSITY=0"])
    args.append(image)
    return args


def run_capsule_in_docker(
    assignment: dict[str, Any],
    *,
    agent_id: str,
    image: str | None = None,
    model_path: Path | None = None,
    model_entry: dict[str, Any] | None = None,
    timeout_sec: float = 600.0,
    docker_bin: str = "docker",
    network_mode: str = "none",
) -> dict[str, Any]:
    verify_assignment_signature(assignment, agent_id)
    resolved_image = image or default_worker_image()
    payload = json.dumps(build_worker_input(assignment), separators=(",", ":"))
    proc = subprocess.run(
        _docker_run_args(
            image=resolved_image,
            model_path=model_path,
            model_entry=model_entry,
            docker_bin=docker_bin,
            network_mode=network_mode,
        ),
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        stdout = proc.stdout.decode("utf-8", errors="replace")
        detail = parse_worker_container_failure(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
        )
        raise RuntimeError(f"worker container failed (exit {proc.returncode}): {detail}")
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
    model_path: Path | None = None,
    model_entry: dict[str, Any] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    resolved_image = image or default_worker_image()

    def _executor(assignment: dict[str, Any]) -> dict[str, Any]:
        return run_capsule_in_docker(
            assignment,
            agent_id=agent_id,
            image=resolved_image,
            model_path=model_path,
            model_entry=model_entry,
        )

    return _executor


def resolve_docker_executor(
    agent_id: str,
    *,
    model_entry: dict[str, Any],
    default_image: str,
    model_path: Path | None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    image = worker_image_for_model(model_entry, default=default_image)
    return docker_capsule_executor(
        agent_id,
        image=image,
        model_path=model_path,
        model_entry=model_entry,
    )
