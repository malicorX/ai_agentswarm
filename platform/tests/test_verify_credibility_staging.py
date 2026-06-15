from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_credibility_staging.py"
PILOT_PARAMS = REPO_ROOT / "docs" / "infra" / "theebie" / "credibility-pilot-params.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_credibility_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_expected_parameters_matches_spec_defaults() -> None:
    mod = _load_module()
    expected = mod.load_expected_parameters()
    assert expected["enabled"] is True
    assert expected["initial_score"] == 10.0
    assert expected["reviewer_mint"] == 2.0


def test_review_parameter_fairness_accepts_pilot_defaults() -> None:
    mod = _load_module()
    params = mod.load_expected_parameters()
    review = mod.review_parameter_fairness(params)
    assert float(review["stake_at_initial"]) == 0.5


def test_verify_credibility_staging_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_CREDIBILITY_ENABLED", "1")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()

    pilot = mod.load_expected_parameters()
    config_resp = MagicMock()
    config_resp.json.return_value = {
        "assignment_mode": "dispatch",
        "credibility": pilot,
    }
    config_resp.raise_for_status = MagicMock()

    cred_resp = MagicMock()
    cred_resp.json.return_value = {
        "agent_id": "agent_cred",
        "project_id": "default",
        "capabilities": [{"capability": "reviewer", "score": 10.0}],
    }
    cred_resp.raise_for_status = MagicMock()

    mock_client.get.side_effect = [health_resp, config_resp, cred_resp]

    identity = MagicMock()
    identity.agent_id = "agent_cred"
    with (
        patch.object(httpx, "Client", return_value=mock_client),
        patch.object(mod, "connect_agent", return_value=identity),
        patch.object(mod.subprocess, "run", return_value=MagicMock(returncode=0)),
    ):
        result = mod.verify_credibility_staging(
            "https://theebie.de/agentswarm/api",
            run_sim_tests=True,
            register_smoke=True,
        )

    assert result["parameters"] == "match_pilot"
    assert result["seed_score"] == "10.0"
    assert result["simulation_tests"] == "passed"
