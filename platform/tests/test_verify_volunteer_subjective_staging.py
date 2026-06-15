from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_volunteer_subjective_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_volunteer_subjective_staging", VERIFY_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_volunteer_subjective_staging_requires_secrets(
    monkeypatch,
) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_VERIFY_SKIP_PREP", "1")
    monkeypatch.delenv("AGENTSWARM_BOOTSTRAP_TOKEN", raising=False)
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "secret")
    try:
        mod.verify_volunteer_subjective_staging("https://theebie.de/agentswarm/api")
    except RuntimeError as exc:
        assert "BOOTSTRAP_TOKEN" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_verify_volunteer_subjective_staging_runs_demo(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_VERIFY_SKIP_PREP", "1")
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "boot")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "secret")

    with patch.object(
        mod,
        "_load_demo_module",
        return_value=type(
            "Demo",
            (),
            {
                "run_volunteer_subjective_demo": staticmethod(
                    lambda url, **kwargs: {
                        "goal_id": "goal-test",
                        "goal_status": "verified",
                        "min_reviewers": kwargs.get("min_reviewers", 1),
                        "model_id": "llm-mock-v1",
                    }
                )
            },
        )(),
    ):
        result = mod.verify_volunteer_subjective_staging(
            "https://theebie.de/agentswarm/api",
            min_reviewers=1,
        )

    assert result["goal_status"] == "verified"
    assert result["goal_id"] == "goal-test"


def test_resolve_subjective_verify_timeouts_defaults(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.delenv("AGENTSWARM_VERIFY_SUBJECTIVE_GOAL_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("AGENTSWARM_VERIFY_SUBJECTIVE_WAIT_SEC", raising=False)
    assert mod.resolve_subjective_verify_timeouts() == (600.0, 60.0)


def test_resolve_subjective_verify_timeouts_from_env(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_VERIFY_SUBJECTIVE_GOAL_TIMEOUT_SEC", "900")
    monkeypatch.setenv("AGENTSWARM_VERIFY_SUBJECTIVE_WAIT_SEC", "45")
    assert mod.resolve_subjective_verify_timeouts() == (900.0, 45.0)


def test_prep_skipped_on_ci_without_ssh(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.delenv("AGENTSWARM_VERIFY_SKIP_PREP", raising=False)
    monkeypatch.delenv("AGENTSWARM_VERIFY_FORCE_PREP", raising=False)
    monkeypatch.setenv("CI", "true")
    with patch.object(mod.subprocess, "run") as mock_run:
        mod.prep_staging_subjective_verify()
    mock_run.assert_not_called()
