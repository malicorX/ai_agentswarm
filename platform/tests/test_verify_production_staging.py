from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_production_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_production_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_production_staging_quick_orchestration() -> None:
    mod = _load_module()

    with (
        patch.object(
            mod,
            "_load_script_module",
            side_effect=[
                type(
                    "PlatformMod",
                    (),
                    {
                        "verify_production_platform": staticmethod(
                            lambda url, **kwargs: {"health": "ok"}
                        )
                    },
                ),
                type(
                    "VersionMod",
                    (),
                    {
                        "verify_agent_versioning_staging": staticmethod(
                            lambda url: {"agent_id": "agent_v"}
                        )
                    },
                ),
                type(
                    "CredMod",
                    (),
                    {
                        "verify_credibility_staging": staticmethod(
                            lambda url, **kwargs: {"seed_score": "10.0"}
                        )
                    },
                ),
                type(
                    "ExternalMod",
                    (),
                    {
                        "verify_external_contributor": staticmethod(
                            lambda url, **kwargs: {"task_flow": "skipped"}
                        )
                    },
                ),
            ],
        ),
        patch.object(mod, "_run_pytest") as mock_pytest,
    ):
        result = mod.verify_production_staging(
            "https://theebie.de/agentswarm/api",
            quick=True,
            expect_dispatch=True,
        )

    assert result["mode"] == "quick"
    assert result["platform"]["health"] == "ok"
    assert result["versioning"]["agent_id"] == "agent_v"
    assert mock_pytest.call_count == 3
