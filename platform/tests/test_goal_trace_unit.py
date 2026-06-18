from __future__ import annotations

from agentswarm_platform.goal_trace import (
    describe_task_work,
    role_label,
    summarize_task_result,
    workspace_ref_for_step,
)


def test_role_label_maps_engineering_pipeline() -> None:
    assert role_label("coordinator.decompose") == "coordinator"
    assert role_label("codewriter.patch") == "codewriter"
    assert role_label("tester.run") == "tester"
    assert role_label("reviewer.approve") == "reviewer"


def test_summarize_task_result() -> None:
    assert "2 immediate" in summarize_task_result(
        "coordinator.decompose",
        {"pool_needs": [{}, {}], "deferred_pool_needs": [{}]},
    )
    assert "applied=True" in summarize_task_result(
        "codewriter.patch",
        {"applied": True, "patch": {"file": "primes.py"}},
    )
    assert "passed=True" in summarize_task_result("tester.run", {"passed": True})
    assert "approved=True" in summarize_task_result("reviewer.approve", {"approved": True})


def test_describe_task_work_engineering() -> None:
    text = describe_task_work(
        "codewriter.patch",
        {
            "capsule": {
                "lab": {"fixture": "primes"},
                "patch": {"file": "primes.py"},
            }
        },
    )
    assert "engineering-lab/primes" in text
    assert "AGENTSWARM_REPO_ROOT" in text


def test_describe_task_work_git_codewriter() -> None:
    text = describe_task_work(
        "codewriter.patch",
        {
            "capsule": {
                "git": {"repo_url": "file:///repo.git"},
                "lab": {"fixture": "primes"},
                "patch": {"file": "primes.py"},
            }
        },
    )
    assert "file:///repo.git" in text
    assert "agentswarm/goal" in text


def test_workspace_ref_for_step_from_result() -> None:
    ref = workspace_ref_for_step(
        "codewriter.patch",
        {},
        {"workspace_ref": "abc123def456", "git_artifact": {"commit_sha": "abc123def456"}},
    )
    assert ref == "abc123def456"


def test_summarize_sandbox_tester_result() -> None:
    text = summarize_task_result(
        "tester.run",
        {
            "passed": True,
            "sandbox": True,
            "run_artifact": {"stdout_digest": "deadbeef" * 8},
        },
    )
    assert "sandbox=true" in text
    assert "digest=" in text


def test_pipeline_phase_mapping() -> None:
    from agentswarm_platform.goal_trace import pipeline_phase, sandbox_host_for_step

    assert pipeline_phase("reviewer.approve") == "review"
    owner = sandbox_host_for_step(
        {"sandbox": True, "run_artifact": {"sandbox_host_owner": "host-a"}}
    )
    assert owner == "host-a"
