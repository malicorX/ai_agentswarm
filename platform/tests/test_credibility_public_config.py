from __future__ import annotations

import pytest

import agentswarm_platform.credibility as credibility
from agentswarm_platform.credibility import public_parameters


def test_public_parameters_includes_spec_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_CREDIBILITY_ENABLED", "1")
    params = public_parameters()
    assert params["enabled"] is True
    assert params["initial_score"] == credibility.INITIAL_SCORE
    assert params["reviewer_mint"] == 2.0
    assert params["stake_min"] == 0.5
    assert "cross_project_haircut" in params
