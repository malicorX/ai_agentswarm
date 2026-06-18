from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_engineering_goal_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_engineering_goal_staging", VERIFY_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_engineering_goal_staging_requires_secrets(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.delenv("AGENTSWARM_BOOTSTRAP_TOKEN", raising=False)
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "secret")
    try:
        mod.verify_engineering_goal_staging("https://theebie.de/agentswarm/api")
    except RuntimeError as exc:
        assert "BOOTSTRAP_TOKEN" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_verify_engineering_goal_staging_runs_demo(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "boot")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "secret")

    with patch.object(
        mod,
        "_load_demo_module",
        return_value=type(
            "Demo",
            (),
            {
                "run_engineering_goal_demo": staticmethod(
                    lambda url, **kwargs: {
                        "goal_id": "goal-eng-test",
                        "goal_status": "verified",
                        "goal_kind": "engineering",
                        "model_id": "llm-mock-v1",
                    }
                )
            },
        )(),
    ):
        result = mod.verify_engineering_goal_staging(
            "https://theebie.de/agentswarm/api",
            fixture="fizzbuzz",
        )

    assert result["goal_status"] == "verified"
    assert result["fixture"] == "fizzbuzz"


def test_resolve_engineering_verify_timeouts_defaults(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.delenv("AGENTSWARM_VERIFY_ENGINEERING_GOAL_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("AGENTSWARM_VERIFY_ENGINEERING_WAIT_SEC", raising=False)
    assert mod.resolve_engineering_verify_timeouts() == (300.0, 60.0)
