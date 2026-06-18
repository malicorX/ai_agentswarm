from __future__ import annotations

from agentswarm_agents.volunteer_executor import assignment_needs_host_executor


def test_git_codewriter_needs_host() -> None:
    assignment = {
        "task_type": "codewriter.patch",
        "capsule": {
            "git": {"repo_url": "root@host:/repo.git"},
            "lab": {"fixture": "primes"},
            "patch": {"file": "primes.py"},
        },
        "verification_spec": {"workspace_mode": "git", "git_in_container": True},
    }
    assert assignment_needs_host_executor(assignment) is True


def test_creative_stays_in_worker_container() -> None:
    assignment = {
        "task_type": "creative.text",
        "capsule": {"brief": "poem"},
    }
    assert assignment_needs_host_executor(assignment) is False


def test_sandbox_tester_needs_host() -> None:
    assignment = {
        "task_type": "tester.run",
        "verification_spec": {"workspace_mode": "sandbox", "fixture": "primes"},
        "capsule": {"verification_spec": {"workspace_mode": "sandbox"}},
    }
    assert assignment_needs_host_executor(assignment) is True


def test_local_fixture_tester_needs_host() -> None:
    assignment = {
        "task_type": "tester.run",
        "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
        "capsule": {
            "goal_id": "goal-abc",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
        },
    }
    assert assignment_needs_host_executor(assignment) is True
