from agentswarm_agents.capsule_executor import execute_capsule


def test_coordinator_capsule_returns_pool_needs_plan() -> None:
    result = execute_capsule(
        {
            "task_type": "coordinator.decompose",
            "capsule": {
                "goal_id": "goal-1",
                "brief": "Write a poem",
                "rubric": [{"id": "quality", "weight": 1.0}],
                "min_reviewers": 3,
            },
        }
    )
    assert result["goal_id"] == "goal-1"
    assert result["pool_needs"][0]["task_type"] == "creative.text"
    assert result["deferred_pool_needs"][0]["spec"]["count"] == 3


def test_reviewer_approve_honors_passing_test_result() -> None:
    result = execute_capsule(
        {
            "task_type": "reviewer.approve",
            "test_result": {"passed": True},
            "capsule": {"goal_id": "goal-1"},
        }
    )
    assert result["approved"] is True
    assert "passing" in result["notes"]


def test_reviewer_approve_rejects_failed_test_result() -> None:
    result = execute_capsule(
        {
            "task_type": "reviewer.approve",
            "test_result": {"passed": False, "stderr": "boom"},
            "capsule": {"goal_id": "goal-1"},
        }
    )
    assert result["approved"] is False
    assert result["notes"] == "tests failed"
