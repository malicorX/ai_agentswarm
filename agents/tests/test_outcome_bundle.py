from __future__ import annotations

from agentswarm_agents.outcome_bundle import build_outcome_bundle

VERIFIED_ENGINEERING_TRACE = {
    "goal_id": "goal-abc",
    "status": "verified",
    "goal_kind": "engineering",
    "brief": "Print first 100 primes",
    "workspace_ref": "d" * 40,
    "artifact_refs": ["sha256:deadbeef"],
    "primary_artifact_ref": "sha256:deadbeef",
    "code_workspace": {"mode": "git", "path": "/tmp/x", "sharing": "forge"},
    "steps": [
        {
            "role": "coordinator",
            "task_type": "coordinator.decompose",
            "result": {"pool_needs": [{"task_type": "codewriter.patch"}], "deferred_pool_needs": []},
        },
        {
            "role": "codewriter",
            "task_type": "codewriter.patch",
            "result": {"applied": True, "file": "primes.py", "workspace_ref": "d" * 40},
        },
        {
            "role": "tester",
            "task_type": "tester.run",
            "result": {
                "passed": True,
                "stdout": "1 passed",
                "stderr": "",
                "run_artifact": {"log_artifact_ref": "sha256:logbundle"},
            },
        },
        {
            "role": "reviewer",
            "task_type": "reviewer.approve",
            "result": {"approved": True, "notes": "ok"},
        },
    ],
}


def test_build_outcome_bundle_engineering_includes_workspace_and_logs() -> None:
    bundle = build_outcome_bundle(VERIFIED_ENGINEERING_TRACE)
    kinds = {item["kind"] for item in bundle["deliverables"]}
    assert bundle["goal_id"] == "goal-abc"
    assert "git_workspace" in kinds
    assert "verification" in kinds
    assert "approval" in kinds
    assert "logs" in kinds
    assert "blob" in kinds
    assert bundle["pipeline_roles"] == ["coordinator", "codewriter", "tester", "reviewer"]


def test_build_outcome_bundle_creative_text() -> None:
    trace = {
        "goal_id": "goal-poem",
        "status": "verified",
        "goal_kind": "creative",
        "brief": "Write a haiku",
        "artifact_text": "line one\nline two",
        "steps": [
            {
                "role": "creative",
                "task_type": "creative.text",
                "result": {"text": "line one\nline two"},
            },
            {
                "role": "reviewer",
                "task_type": "reviewer.subjective",
                "result": {"scores": {"quality": 8.0}, "rationale": "nice"},
            },
        ],
    }
    bundle = build_outcome_bundle(trace)
    kinds = {item["kind"] for item in bundle["deliverables"]}
    assert "text" in kinds
    assert "scores" in kinds
