from __future__ import annotations

import pytest

from agentswarm_platform.coordinator_plan import (
    build_default_creative_goal_plan,
    build_default_engineering_goal_plan,
    goal_allows_same_agent_pipeline,
    materialize_deferred_payload,
    resolve_pool_need_constraints,
    validate_coordinator_plan,
)


GOAL = {
    "goal_id": "goal-abc",
    "poster_agent_id": "agent-poster",
    "brief": "Write a poem",
    "rubric": [{"id": "quality", "weight": 1.0}],
    "min_reviewers": 3,
}


def test_build_default_creative_goal_plan() -> None:
    plan = build_default_creative_goal_plan(GOAL)
    assert plan["goal_id"] == "goal-abc"
    assert len(plan["pool_needs"]) == 1
    assert plan["pool_needs"][0]["task_type"] == "creative.text"
    assert len(plan["deferred_pool_needs"]) == 1
    assert plan["deferred_pool_needs"][0]["after_task_type"] == "creative.text"
    assert plan["deferred_pool_needs"][0]["spec"]["count"] == 3


def test_validate_coordinator_plan_rejects_missing_pool_needs() -> None:
    with pytest.raises(ValueError, match="pool_needs"):
        validate_coordinator_plan({"goal_id": "goal-abc"}, goal_id="goal-abc")


def test_build_default_engineering_goal_plan_fizzbuzz() -> None:
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": "goal-fizz",
            "brief": "FizzBuzz",
            "verification_spec": {"fixture": "fizzbuzz", "lab": "engineering-lab"},
        }
    )
    assert plan["pool_needs"][0]["payload"]["capsule"]["patch"]["file"] == "fizzbuzz.py"
    validate_coordinator_plan(plan, goal_id="goal-fizz", goal_kind="engineering")


def test_build_default_engineering_goal_plan_sandbox() -> None:
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": "goal-sandbox",
            "brief": "Primes in sandbox",
            "verification_spec": {
                "fixture": "primes",
                "lab": "engineering-lab",
                "workspace_mode": "sandbox",
            },
        }
    )
    assert len(plan["deferred_pool_needs"]) == 3
    builder_spec = plan["deferred_pool_needs"][0]["spec"]
    assert builder_spec["task_type"] == "builder.compile"
    assert builder_spec["capability_required"] == "sandbox.build"
    tester_spec = plan["deferred_pool_needs"][1]["spec"]
    assert tester_spec["capability_required"] == "sandbox.test"
    assert plan["deferred_pool_needs"][1]["after_task_type"] == "builder.compile"
    validate_coordinator_plan(plan, goal_id="goal-sandbox", goal_kind="engineering")


def test_build_default_engineering_goal_plan_high_risk_reviewer_vram() -> None:
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": "goal-risky",
            "brief": "High-risk primes",
            "verification_spec": {
                "fixture": "primes",
                "lab": "engineering-lab",
                "workspace_mode": "sandbox",
                "risk_level": "high",
            },
        }
    )
    reviewer_spec = plan["deferred_pool_needs"][-1]["spec"]
    assert reviewer_spec["constraints"]["min_reviewer_vram_gb"] == 12.0
    assert reviewer_spec["payload_template"]["replication"] == {"slots": 2, "quorum": 2}


def test_build_default_engineering_goal_plan_high_risk_replication_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_HIGH_RISK_REVIEWER_SLOTS", "3")
    monkeypatch.setenv("AGENTSWARM_HIGH_RISK_REVIEWER_QUORUM", "2")
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": "goal-risky",
            "brief": "High-risk primes",
            "verification_spec": {
                "fixture": "primes",
                "lab": "engineering-lab",
                "workspace_mode": "sandbox",
                "risk_level": "high",
            },
        }
    )
    replication = plan["deferred_pool_needs"][-1]["spec"]["payload_template"]["replication"]
    assert replication == {"slots": 3, "quorum": 2}


def test_build_default_engineering_goal_plan_windows() -> None:
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": "goal-win",
            "brief": "Primes in Windows VM",
            "verification_spec": {
                "fixture": "primes",
                "lab": "engineering-lab",
                "workspace_mode": "windows",
            },
        }
    )
    assert len(plan["deferred_pool_needs"]) == 3
    builder_spec = plan["deferred_pool_needs"][0]["spec"]
    assert builder_spec["capability_required"] == "sandbox.windows.build"
    tester_spec = plan["deferred_pool_needs"][1]["spec"]
    assert tester_spec["capability_required"] == "sandbox.windows.test"
    validate_coordinator_plan(plan, goal_id="goal-win", goal_kind="engineering")


def test_build_default_engineering_goal_plan_git_in_container() -> None:
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": "goal-git-sandbox",
            "brief": "Primes via git sandbox",
            "verification_spec": {
                "fixture": "primes",
                "workspace_mode": "git",
                "git_in_container": True,
            },
            "workspace": {
                "mode": "git",
                "repo_url": "file:///tmp/primes.git",
                "default_branch": "main",
            },
        }
    )
    capsule = plan["pool_needs"][0]["payload"]["capsule"]
    assert capsule.get("sandbox_git") is True
    tester_spec = plan["deferred_pool_needs"][0]["spec"]
    assert tester_spec["capability_required"] == "sandbox.test"


def test_build_default_engineering_goal_plan_git() -> None:
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": "goal-git",
            "brief": "Primes via git",
            "verification_spec": {
                "fixture": "primes",
                "workspace_mode": "git",
            },
            "workspace": {
                "mode": "git",
                "repo_url": "file:///tmp/primes.git",
                "default_branch": "main",
            },
        }
    )
    capsule = plan["pool_needs"][0]["payload"]["capsule"]
    assert "git" in capsule
    assert capsule["git"]["repo_url"] == "file:///tmp/primes.git"
    tester_spec = plan["deferred_pool_needs"][0]["spec"]
    assert tester_spec["capability_required"] == "tester"
    validate_coordinator_plan(plan, goal_id="goal-git", goal_kind="engineering")


def test_build_default_engineering_goal_plan_rejects_creative_task_type() -> None:
    plan = build_default_creative_goal_plan(GOAL)
    plan["pool_needs"][0]["task_type"] = "codewriter.patch"
    with pytest.raises(ValueError, match="not allowed"):
        validate_coordinator_plan(plan, goal_id="goal-abc")


def test_materialize_deferred_payload_injects_artifact() -> None:
    template = {
        "goal_id": "goal-abc",
        "capsule": {"goal_id": "goal-abc", "brief": "Write a poem"},
    }
    payload = materialize_deferred_payload(
        template,
        goal={**GOAL, "artifact_text": "Poem body"},
    )
    assert payload["capsule"]["artifact_text"] == "Poem body"


def test_materialize_deferred_payload_injects_parent_test_result() -> None:
    template = {
        "goal_id": "goal-abc",
        "capsule": {"goal_id": "goal-abc", "brief": "Print primes"},
    }
    test_result = {"passed": True, "fixture": "primes"}
    payload = materialize_deferred_payload(
        template,
        goal=GOAL,
        parent_test_result=test_result,
        parent_task_id="task-tester-1",
    )
    assert payload["test_result"] == test_result
    assert payload["capsule"]["test_result"] == test_result
    assert payload["parent_task_id"] == "task-tester-1"


def test_resolve_pool_need_constraints_exclude_flags() -> None:
    distributed_goal = {
        **GOAL,
        "dispatch_include_owners": ["vol-a"],
        "verification_spec": {"solo_pipeline": False},
    }
    resolved = resolve_pool_need_constraints(
        {"exclude_poster": True, "exclude_worker": True},
        goal=distributed_goal,
        poster_owner="poster-owner",
        worker_agent_id="agent-worker",
    )
    assert "poster-owner" in resolved["exclude_owners"]
    assert "agent-poster" in resolved["exclude_agent_ids"]
    assert "agent-worker" in resolved["exclude_agent_ids"]


def test_resolve_pool_need_constraints_solo_pipeline_allows_worker() -> None:
    goal = {**GOAL, "dispatch_include_owners": [], "verification_spec": {}}
    assert goal_allows_same_agent_pipeline(goal) is True
    resolved = resolve_pool_need_constraints(
        {"exclude_poster": True, "exclude_worker": True},
        goal=goal,
        poster_owner="poster-owner",
        worker_agent_id="agent-worker",
    )
    assert "poster-owner" in resolved["exclude_owners"]
    assert "agent-poster" in resolved["exclude_agent_ids"]
    assert "agent-worker" not in resolved["exclude_agent_ids"]


def test_goal_allows_same_agent_pipeline_respects_explicit_false() -> None:
    goal = {
        **GOAL,
        "dispatch_include_owners": [],
        "verification_spec": {"solo_pipeline": False},
    }
    assert goal_allows_same_agent_pipeline(goal) is False


def test_resolve_pool_need_constraints_merges_goal_include_owners() -> None:
    resolved = resolve_pool_need_constraints(
        {"exclude_poster": True},
        goal={**GOAL, "dispatch_include_owners": ["demo-coordinator-run"]},
        poster_owner="poster-owner",
        worker_agent_id=None,
    )
    assert resolved["include_owners"] == ["demo-coordinator-run"]
