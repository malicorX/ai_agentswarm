from __future__ import annotations

from agentswarm_agents.goal_run_log import analyze_goal_run
from agentswarm_agents.replay_goal import merge_trace_into_context


def test_analyze_missing_workspace_ref() -> None:
    trace = {
        "goal_id": "goal-git-missing",
        "status": "pending",
        "goal_kind": "engineering",
        "steps": [
            {
                "task_type": "codewriter.patch",
                "status": "verified",
                "submitted_at": "2026-01-01T00:00:00Z",
                "result": {"applied": True, "file": "primes.py"},
            }
        ],
    }
    ctx = {
        "goal_id": "goal-git-missing",
        "verification_spec": {"workspace_mode": "git", "fixture": "primes"},
    }
    issues = analyze_goal_run(trace, ctx)
    codes = {item["code"] for item in issues}
    assert "missing_workspace_ref" in codes


def test_analyze_reviewer_approved_but_goal_pending() -> None:
    trace = {
        "goal_id": "goal-stuck",
        "status": "pending",
        "steps": [
            {
                "task_type": "reviewer.approve",
                "status": "verified",
                "submitted_at": "2026-01-01T00:01:00Z",
                "result": {"approved": True},
            }
        ],
    }
    issues = analyze_goal_run(trace, {"goal_id": "goal-stuck"})
    assert any(item["code"] == "goal_stuck_after_reviewer" for item in issues)


def test_merge_trace_harvests_workspace_ref_from_step() -> None:
    ctx = {"goal_id": "goal-x", "verification_spec": {"workspace_mode": "git"}}
    trace = {
        "steps": [
            {
                "task_type": "codewriter.patch",
                "workspace_ref": "a" * 40,
                "result": {"workspace_ref": "a" * 40, "applied": True},
            }
        ]
    }
    merged = merge_trace_into_context(ctx, trace)
    assert merged["workspace_ref"] == "a" * 40
