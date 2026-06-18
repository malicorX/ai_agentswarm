from __future__ import annotations

from agentswarm_agents.volunteer_work import (
    role_from_assignment,
    summarize_work_result,
    work_context_from_assignment,
    work_label_from_assignment,
)


def test_work_context_from_engineering_assignment() -> None:
    assignment = {
        "task_id": "task_abc123",
        "task_type": "codewriter.patch",
        "capability_required": "codewriter",
        "project_id": "default",
        "capsule": {
            "goal_id": "goal-eng001",
            "lab": {"fixture": "primes"},
        },
    }
    ctx = work_context_from_assignment(assignment)
    assert ctx.role == "codewriter"
    assert ctx.goal_id == "goal-eng001"
    assert ctx.project_id == "default"
    assert ctx.label == "fixture:primes"


def test_role_falls_back_to_task_type_prefix() -> None:
    assignment = {"task_type": "tester.run", "task_id": "task_1"}
    assert role_from_assignment(assignment) == "tester"


def test_summarize_tester_result() -> None:
    summary, detail = summarize_work_result(
        "tester.run",
        {"passed": False, "stderr": "AssertionError"},
    )
    assert summary == "tests failed"
    assert "AssertionError" in detail


def test_work_label_from_brief() -> None:
    assignment = {"capsule": {"brief": "Write a haiku about rain"}}
    assert work_label_from_assignment(assignment) == "Write a haiku about rain"
