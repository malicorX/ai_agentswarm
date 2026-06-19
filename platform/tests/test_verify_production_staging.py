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
    reg_auth_calls: list[dict] = []

    def capture_reg_auth(url: str, **kwargs: object) -> dict[str, str]:
        reg_auth_calls.append(dict(kwargs))
        return {"anonymous_register": "rejected"}

    def capture_dispatch(url: str, **kwargs: object) -> dict[str, str]:
        return {"assignment_mode": "dispatch", "presence": "idle"}

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
                            lambda url, **kwargs: {
                                "health": "ok",
                                "auth_enforced": "true",
                                "assignment_mode": "dispatch",
                            }
                        )
                    },
                ),
                type(
                    "DispatchMod",
                    (),
                    {"verify_dispatch_staging": staticmethod(capture_dispatch)},
                ),
                type(
                    "SdkDispatchMod",
                    (),
                    {
                        "verify_sdk_dispatch_staging": staticmethod(
                            lambda url: {"register": "agent_sdk"}
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
                    "RegAuthMod",
                    (),
                    {"verify_registration_auth_staging": staticmethod(capture_reg_auth)},
                ),
                type(
                    "ModelMod",
                    (),
                    {
                        "verify_model_allowlist_staging": staticmethod(
                            lambda url, **kwargs: {"allowed_model_presence": "ok"}
                        )
                    },
                ),
                type(
                    "HardwareMod",
                    (),
                    {
                        "verify_hardware_gates_staging": staticmethod(
                            lambda url, **kwargs: {"low_vram_rejected": "skipped"}
                        )
                    },
                ),
                type(
                    "GoalDeployMod",
                    (),
                    {
                        "verify_goal_deploy_staging": staticmethod(
                            lambda url: {"deploy_request": "ok"}
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
    assert result["dispatch"]["assignment_mode"] == "dispatch"
    assert result["sdk_dispatch"]["register"] == "agent_sdk"
    assert result["versioning"]["agent_id"] == "agent_v"
    assert result["goal_deploy"]["deploy_request"] == "ok"
    assert reg_auth_calls == [{"expect_enforced": True}]
    assert mock_pytest.call_count == 6
