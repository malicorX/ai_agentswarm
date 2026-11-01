"""E2E: dispatch posts a goal -> one generalist volunteer claims and completes it.

These tests mirror the task-console + volunteer GUI flow (solo machine, all roles).
Run the full volunteer dispatch suite:

  pytest agents/tests/test_volunteer_dispatch_e2e.py agents/tests/test_task_pool_chain_e2e.py -m dispatch_e2e
"""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest

from agentswarm_agents.create_task import create_goal_from_spec
from agentswarm_agents.engineering_lab import reset_fixture
from agentswarm_agents.sandbox_executor import docker_available, ensure_sandbox_test_image
from agentswarm_agents.start_task import (
    create_and_execute_with_generalist_volunteer,
    execute_goal_with_generalist_volunteer,
)
from agentswarm_agents.task_file import load_task_file

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PRIMES_TASK = REPO_ROOT / "tasks" / "example-primes.txt"
EXAMPLE_PRIMES_GIT_SANDBOX_TASK = REPO_ROOT / "tasks" / "example-primes-git-sandbox.txt"

pytestmark = pytest.mark.dispatch_e2e


def _assert_engineering_pipeline_verified(trace: dict) -> None:
    roles = [step["role"] for step in trace["steps"]]
    assert "coordinator" in roles
    assert "codewriter" in roles
    assert "tester" in roles
    assert "reviewer" in roles
    for step in trace["steps"]:
        assert step["status"] in ("verified", "submitted", "rejected", "passed", "failed")


def test_dispatch_goal_generalist_volunteer_primes_verified(
    live_dispatch_platform: str,
    e2e_dispatch_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_task -> single volunteer (all roles) -> verified local fixture goal."""
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))
    reset_fixture("primes")

    spec = load_task_file(EXAMPLE_PRIMES_TASK)
    created = create_goal_from_spec(live_dispatch_platform, spec)
    goal_id = created["goal_id"]

    goal = execute_goal_with_generalist_volunteer(
        live_dispatch_platform,
        goal_id,
        model_id="llm-mock-v1",
        owner="volunteer-solo",
        wait_timeout_sec=10.0,
        goal_timeout_sec=120.0,
        worker_ready_timeout_sec=45.0,
        realign_dispatch=False,
    )

    assert goal["status"] == "verified"
    assert goal.get("artifact_text")

    trace = httpx.get(
        f"{live_dispatch_platform}/creative/goals/{goal_id}/trace"
    ).json()
    _assert_engineering_pipeline_verified(trace)


def test_dispatch_task_file_generalist_one_liner_verified(
    live_dispatch_platform: str,
    e2e_dispatch_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_and_execute_with_generalist_volunteer covers post + volunteer in one call."""
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))
    reset_fixture("primes")

    goal = create_and_execute_with_generalist_volunteer(
        live_dispatch_platform,
        EXAMPLE_PRIMES_TASK,
        model_id="llm-mock-v1",
        owner="volunteer-one-shot",
        wait_timeout_sec=10.0,
        goal_timeout_sec=120.0,
        worker_ready_timeout_sec=45.0,
    )

    assert goal["status"] == "verified"


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_dispatch_goal_generalist_git_in_container_verified(
    live_dispatch_platform: str,
    e2e_dispatch_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Git + sandbox pytest on host (catches docker-worker mis-routing for tester)."""
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))
    ensure_sandbox_test_image()

    spec = load_task_file(EXAMPLE_PRIMES_GIT_SANDBOX_TASK)
    created = create_goal_from_spec(live_dispatch_platform, spec)
    goal_id = created["goal_id"]

    goal = execute_goal_with_generalist_volunteer(
        live_dispatch_platform,
        goal_id,
        model_id="llm-mock-v1",
        owner="volunteer-git-solo",
        wait_timeout_sec=15.0,
        goal_timeout_sec=240.0,
        worker_ready_timeout_sec=90.0,
        realign_dispatch=False,
    )

    assert goal["status"] == "verified"
    trace = httpx.get(
        f"{live_dispatch_platform}/creative/goals/{goal_id}/trace"
    ).json()
    assert trace.get("code_workspace", {}).get("mode") == "git"
    tester = next(s for s in trace["steps"] if s["role"] == "tester")
    assert tester["status"] in ("verified", "submitted", "passed", "failed")
