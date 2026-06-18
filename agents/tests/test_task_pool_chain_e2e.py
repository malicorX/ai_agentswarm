"""Live-platform end-to-end tests: create_task -> volunteer clients -> verified goal."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from agentswarm_agents.create_task import create_goal_from_spec
from agentswarm_agents.engineering_lab import reset_fixture
from agentswarm_agents.sandbox_executor import docker_available, ensure_sandbox_test_image
from agentswarm_agents.start_task import execute_goal_with_volunteers
from agentswarm_agents.task_file import load_task_file

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PRIMES_TASK = REPO_ROOT / "tasks" / "example-primes.txt"
EXAMPLE_PRIMES_GIT_TASK = REPO_ROOT / "tasks" / "example-primes-git.txt"
EXAMPLE_PRIMES_SANDBOX_TASK = REPO_ROOT / "tasks" / "example-primes-sandbox.txt"
E2E_ASSIGNMENT_SECRET = "test-dispatch-secret-e2e"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, *, timeout_sec: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001 - probe until ready
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"platform did not become healthy at {base_url}: {last_error}")


@pytest.fixture
def live_dispatch_platform(tmp_path: Path) -> str:
    """Start uvicorn with dispatch mode for volunteer-client integration tests."""
    db_path = tmp_path / "platform.db"
    identity_dir = tmp_path / "identities"
    identity_dir.mkdir()
    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env.update(
        {
            "AGENTSWARM_DB": str(db_path),
            "AGENTSWARM_ARTIFACT_DIR": str(tmp_path / "artifacts"),
            "AGENTSWARM_AUTH_DISABLED": "1",
            "AGENTSWARM_ASSIGNMENT_MODE": "dispatch",
            "AGENTSWARM_ASSIGNMENT_SECRET": E2E_ASSIGNMENT_SECRET,
            "AGENTSWARM_IDENTITY_DIR": str(identity_dir),
        }
    )

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "agentswarm_platform.main:app",
        "--app-dir",
        str(REPO_ROOT / "platform" / "src"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(base_url)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest.fixture
def e2e_dispatch_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", E2E_ASSIGNMENT_SECRET)
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "e2e-bootstrap")
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))


def test_create_task_volunteer_chain_primes_verified(
    live_dispatch_platform: str,
    e2e_dispatch_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Full chain: task file -> pool -> volunteer clients -> verified engineering goal."""
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))
    reset_fixture("primes")

    spec = load_task_file(EXAMPLE_PRIMES_TASK)
    created = create_goal_from_spec(live_dispatch_platform, spec)
    goal_id = created["goal_id"]
    assert created["status"] == "pending"
    assert created["coordinator_task_id"]

    goal = execute_goal_with_volunteers(
        live_dispatch_platform,
        goal_id,
        model_id="llm-mock-v1",
        wait_timeout_sec=10.0,
        goal_timeout_sec=120.0,
        worker_ready_timeout_sec=45.0,
        owner_prefix="chain-e2e",
    )

    assert goal["status"] == "verified"
    assert goal["goal_kind"] == "engineering"
    assert goal.get("goal_id") == goal_id
    assert goal.get("artifact_text")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_create_task_volunteer_chain_git_verified(
    live_dispatch_platform: str,
    e2e_dispatch_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Git workspace: codewriter commit -> workspace_ref -> tester checkout -> verified."""
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))

    spec = load_task_file(EXAMPLE_PRIMES_GIT_TASK)
    created = create_goal_from_spec(live_dispatch_platform, spec)
    goal_id = created["goal_id"]

    goal = execute_goal_with_volunteers(
        live_dispatch_platform,
        goal_id,
        model_id="llm-mock-v1",
        wait_timeout_sec=10.0,
        goal_timeout_sec=120.0,
        worker_ready_timeout_sec=45.0,
        owner_prefix="git-e2e",
    )

    assert goal["status"] == "verified"
    assert goal.get("workspace_ref")

    trace = httpx.get(f"{live_dispatch_platform}/creative/goals/{goal_id}/trace").json()
    assert trace.get("workspace_ref")
    assert trace.get("code_workspace", {}).get("mode") == "git"
    codewriter = next(s for s in trace["steps"] if s["role"] == "codewriter")
    tester = next(s for s in trace["steps"] if s["role"] == "tester")
    assert codewriter.get("workspace_ref")
    assert tester.get("workspace_ref") == codewriter.get("workspace_ref")


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
def test_create_task_volunteer_chain_sandbox_verified(
    live_dispatch_platform: str,
    e2e_dispatch_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Sandbox: codewriter -> builder.compile -> tester.run in Docker -> verified."""
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))
    reset_fixture("primes")
    ensure_sandbox_test_image()

    spec = load_task_file(EXAMPLE_PRIMES_SANDBOX_TASK)
    created = create_goal_from_spec(live_dispatch_platform, spec)
    goal_id = created["goal_id"]

    goal = execute_goal_with_volunteers(
        live_dispatch_platform,
        goal_id,
        model_id="llm-mock-v1",
        wait_timeout_sec=15.0,
        goal_timeout_sec=240.0,
        worker_ready_timeout_sec=90.0,
        owner_prefix="sandbox-e2e",
    )

    assert goal["status"] == "verified"

    trace = httpx.get(f"{live_dispatch_platform}/creative/goals/{goal_id}/trace").json()
    roles = [step["role"] for step in trace["steps"]]
    assert "builder" in roles
    assert "tester" in roles
    builder = next(s for s in trace["steps"] if s["role"] == "builder")
    tester = next(s for s in trace["steps"] if s["role"] == "tester")
    assert builder.get("phase") == "build"
    assert builder.get("sandbox_host_owner")
    assert tester.get("sandbox_host_owner")
    if builder.get("log_artifact_ref"):
        assert builder["log_artifact_ref"].startswith("sha256:")
