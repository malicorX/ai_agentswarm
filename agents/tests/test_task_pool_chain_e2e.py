"""Live-platform end-to-end tests: create_task -> volunteer clients -> verified goal."""

from __future__ import annotations

import shutil
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

pytestmark = pytest.mark.dispatch_e2e


def test_create_task_volunteer_chain_primes_verified(
    live_dispatch_platform: str,
    e2e_dispatch_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Full chain: task file -> multi-role volunteer team -> verified engineering goal."""
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
