from __future__ import annotations

import json

import pytest

from agentswarm_platform.credit_pricing import (
    load_pricing_table,
    post_cost,
    public_parameters,
    reviewer_reward_for,
)


def test_default_pricing_table() -> None:
    table = load_pricing_table()
    assert table["creative.goal"]["post_cost"] == 50.0
    assert table["reviewer.subjective"]["reviewer_reward"] == 15.0
    assert table["git.patch"]["post_cost"] == 30.0


def test_env_overrides_goal_and_reward(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_CREDITS_GOAL_COST", "40")
    monkeypatch.setenv("AGENTSWARM_CREDITS_REVIEWER_REWARD", "12")
    table = load_pricing_table()
    assert table["creative.goal"]["post_cost"] == 40.0
    assert reviewer_reward_for("reviewer.subjective") == 12.0


def test_pricing_json_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENTSWARM_CREDITS_PRICING_JSON",
        json.dumps({"creative.goal": {"post_cost": 25}, "custom.task": {"post_cost": 9}}),
    )
    table = load_pricing_table()
    assert table["creative.goal"]["post_cost"] == 25.0
    assert table["custom.task"]["post_cost"] == 9.0
    assert post_cost("custom.task") == 9.0


def test_post_cost_scales_with_difficulty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_CREDITS_GOAL_COST", "20")
    assert post_cost("creative.goal", difficulty=2.0) == 40.0


def test_public_parameters_includes_pricing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    params = public_parameters()
    assert params["enabled"] is True
    assert params["initial"] == 100.0
    assert "creative.goal" in params["pricing"]
