from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_volunteer_subjective.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("demo_volunteer_subjective", DEMO_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_demo_platform_requires_dispatch() -> None:
    mod = _load_module()
    with pytest.raises(RuntimeError, match="dispatch"):
        mod.validate_demo_platform({"assignment_mode": "pull"})


def test_validate_demo_platform_returns_allowlisted_model() -> None:
    mod = _load_module()
    model_id = mod.validate_demo_platform(
        {"assignment_mode": "dispatch", "models": {"enforced": True}}
    )
    assert model_id == "llm-mock-v1"


def test_run_volunteer_subjective_demo_e2e() -> None:
    mod = _load_module()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    config_resp = MagicMock()
    config_resp.raise_for_status = MagicMock()
    config_resp.json.return_value = {
        "assignment_mode": "dispatch",
        "models": {"enforced": True},
    }
    mock_client.get.return_value = config_resp

    with (
        patch.object(mod.httpx, "Client", return_value=mock_client),
        patch.object(mod, "run_volunteer_role", return_value=True) as run_role,
        patch.object(mod.time, "sleep"),
        patch.object(
            mod,
            "register_poster_and_create_goal",
            return_value=("poster-1", "goal-demo-1"),
        ),
        patch.object(
            mod,
            "wait_for_goal",
            return_value={"status": "verified", "aggregate_score": 8.0},
        ),
    ):
        result = mod.run_volunteer_subjective_demo(
            "https://theebie.de/agentswarm/api",
            min_reviewers=2,
        )

    assert result["goal_id"] == "goal-demo-1"
    assert result["goal_status"] == "verified"
    assert run_role.call_count == 4  # coordinator + creative + 2 reviewers
