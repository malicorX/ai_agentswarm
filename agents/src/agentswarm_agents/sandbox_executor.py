"""Run engineering tests inside an ephemeral OCI container (D2)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from agentswarm_agents.client import repo_root
from agentswarm_agents.engineering_lab import engineering_lab_root, fixture_dir
from agentswarm_agents.sandbox_security import (
    cleanup_sandbox_container,
    docker_security_args,
    sandbox_container_name,
)

DEFAULT_SANDBOX_IMAGE = "agentswarm/sandbox-pytest:3.12.2"
DEFAULT_SANDBOX_DOCKERFILE = Path("pilot") / "engineering-lab" / "Dockerfile.sandbox"
DEFAULT_MEMORY = "512m"
DEFAULT_NETWORK = "none"


def docker_available() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def sandbox_image_ref(verification_spec: dict[str, Any] | None = None) -> str:
    if verification_spec and verification_spec.get("sandbox_image"):
        return str(verification_spec["sandbox_image"])
    return DEFAULT_SANDBOX_IMAGE


def ensure_sandbox_test_image(
    image: str | None = None,
    *,
    build_context: Path | None = None,
) -> str:
    """Build the default sandbox image locally when missing."""
    resolved = image or DEFAULT_SANDBOX_IMAGE
    if resolved != DEFAULT_SANDBOX_IMAGE:
        return resolved
    inspect = subprocess.run(
        ["docker", "image", "inspect", resolved],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode == 0:
        return resolved
    if not docker_available():
        raise RuntimeError("Docker is not available; cannot build sandbox test image")
    context = build_context or Path(repo_root())
    dockerfile = context / DEFAULT_SANDBOX_DOCKERFILE
    if not dockerfile.is_file():
        raise FileNotFoundError(f"sandbox Dockerfile not found: {dockerfile}")
    subprocess.run(
        [
            "docker",
            "build",
            "-t",
            resolved,
            "-f",
            str(dockerfile),
            str(context),
        ],
        check=True,
    )
    return resolved


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sandbox_run_id(verification_spec: dict[str, Any]) -> str | None:
    raw = verification_spec.get("sandbox_run_id")
    if raw is None:
        return None
    cleaned = str(raw).strip()
    return cleaned or None


def _docker_run_cmd(
    *,
    verification_spec: dict[str, Any],
    image: str,
    host_path: str,
    container_work: str,
    memory_limit: str,
    network: str,
    command: list[str],
    extra_env: list[str] | None = None,
) -> list[str]:
    run_id = _sandbox_run_id(verification_spec)
    cleanup_sandbox_container(run_id)
    cmd = [
        "docker",
        "run",
        "--rm",
        f"--network={network}",
        f"--memory={memory_limit}",
        "--pids-limit=256",
        *docker_security_args(),
    ]
    if run_id:
        cmd.extend(["--name", sandbox_container_name(run_id)])
    if extra_env:
        cmd.extend(extra_env)
    cmd.extend(
        [
            "-v",
            f"{host_path}:{container_work}:ro",
            "-w",
            container_work,
            image,
            *command,
        ]
    )
    return cmd


def run_sandbox_command(
    *,
    verification_spec: dict[str, Any],
    image: str,
    command: list[str],
    volume_mounts: list[tuple[str, str, str]],
    container_workdir: str = "/work",
    memory_limit: str = DEFAULT_MEMORY,
    network: str = DEFAULT_NETWORK,
    extra_env: list[str] | None = None,
    input_text: str | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    """Run an arbitrary command in a sandbox container with custom volume mounts."""
    run_id = _sandbox_run_id(verification_spec)
    cleanup_sandbox_container(run_id)
    cmd: list[str] = [
        "docker",
        "run",
        "--rm",
        "-i",
        f"--network={network}",
        f"--memory={memory_limit}",
        "--pids-limit=256",
        *docker_security_args(),
    ]
    if run_id:
        cmd.extend(["--name", sandbox_container_name(run_id)])
    if extra_env:
        cmd.extend(extra_env)
    for host_path, container_path, mode in volume_mounts:
        cmd.extend(["-v", f"{host_path}:{container_path}:{mode}"])
    cmd.extend(["-w", container_workdir, image, *command])
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def run_fixture_tests_sandbox(
    verification_spec: dict[str, Any],
    *,
    image: str | None = None,
    memory_limit: str = DEFAULT_MEMORY,
    network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    """Execute pytest for an engineering-lab fixture inside Docker."""
    if not docker_available():
        raise RuntimeError(
            "Docker is not available; install Docker or use workspace_mode=local_fixture"
        )
    fixture = str(verification_spec.get("fixture", "primes"))
    host_fixture = fixture_dir(fixture)
    if not host_fixture.is_dir():
        raise FileNotFoundError(f"engineering fixture not found: {fixture}")

    resolved_image = ensure_sandbox_test_image(
        image or sandbox_image_ref(verification_spec)
    )
    host_path = str(host_fixture.resolve())
    container_work = "/work"
    cmd = _docker_run_cmd(
        verification_spec=verification_spec,
        image=resolved_image,
        host_path=host_path,
        container_work=container_work,
        memory_limit=memory_limit,
        network=network,
        command=["python", "-m", "pytest", "tests", "-q", "-p", "no:faulthandler"],
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=300)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "fixture": fixture,
        "sandbox": True,
        "sandbox_image": resolved_image,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "run_artifact": {
            "passed": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout_digest": _digest_text(stdout),
            "stderr_digest": _digest_text(stderr),
            "sandbox_image": resolved_image,
            "fixture": fixture,
        },
    }


def run_compile_sandbox(
    verification_spec: dict[str, Any],
    *,
    image: str | None = None,
    memory_limit: str = DEFAULT_MEMORY,
    network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    """Compile-check engineering-lab sources inside Docker (builder.compile)."""
    if not docker_available():
        raise RuntimeError(
            "Docker is not available; install Docker or use workspace_mode=local_fixture"
        )
    fixture = str(verification_spec.get("fixture", "primes"))
    host_fixture = fixture_dir(fixture)
    if not host_fixture.is_dir():
        raise FileNotFoundError(f"engineering fixture not found: {fixture}")

    resolved_image = ensure_sandbox_test_image(
        image or sandbox_image_ref(verification_spec)
    )
    host_path = str(host_fixture.resolve())
    container_work = "/work"
    # Fixture mount is read-only; redirect .pyc writes away from the workspace.
    command = ["python", "-m", "compileall", "-q", "."]
    cmd = _docker_run_cmd(
        verification_spec=verification_spec,
        image=resolved_image,
        host_path=host_path,
        container_work=container_work,
        memory_limit=memory_limit,
        network=network,
        command=command,
        extra_env=["-e", "PYTHONPYCACHEPREFIX=/tmp/pycache"],
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=300)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "fixture": fixture,
        "sandbox": True,
        "sandbox_image": resolved_image,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "build_artifact": {
            "passed": proc.returncode == 0,
            "command": " ".join(command),
            "stdout_digest": _digest_text(stdout),
            "stderr_digest": _digest_text(stderr),
            "sandbox_image": resolved_image,
            "fixture": fixture,
        },
    }
