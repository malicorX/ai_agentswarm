from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_staging_deploy_e2e.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_staging_deploy_e2e", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_staging_deploy_e2e_goal_deploy_ok() -> None:
    mod = _load_module()
    with (
        patch.object(
            mod,
            "_load_script_module",
            side_effect=lambda name, path: type(
                "Stub",
                (),
                {
                    "verify_goal_deploy_staging": staticmethod(
                        lambda _url: {"deploy_from_goal": "ok"}
                    )
                },
            )(),
        ),
        patch.object(mod, "_env_flag", return_value=False),
    ):
        result = mod.verify_staging_deploy_e2e("https://theebie.de/agentswarm/api")
    assert result["goal_deploy"]["deploy_from_goal"] == "ok"


def test_verify_staging_deploy_e2e_rejects_not_deployed() -> None:
    mod = _load_module()
    with (
        patch.object(
            mod,
            "_load_script_module",
            side_effect=lambda name, path: type(
                "Stub",
                (),
                {
                    "verify_goal_deploy_staging": staticmethod(
                        lambda _url: {"deploy_from_goal": "skipped_not_deployed"}
                    )
                },
            )(),
        ),
        patch.object(mod, "_env_flag", return_value=False),
    ):
        with pytest.raises(RuntimeError, match="not deployed"):
            mod.verify_staging_deploy_e2e("https://theebie.de/agentswarm/api")
