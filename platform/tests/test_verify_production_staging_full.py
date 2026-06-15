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


def test_verify_production_staging_full_orchestration() -> None:
    mod = _load_module()
    appeal_calls: list[str] = []

    def capture_appeal(url: str, **kwargs: object) -> dict[str, str]:
        appeal_calls.append(url)
        return {"get_missing_goal": "404"}

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
                    {"verify_dispatch_staging": staticmethod(lambda url: {"register": "ok"})},
                ),
                type(
                    "VersionMod",
                    (),
                    {"verify_agent_versioning_staging": staticmethod(lambda url: {"ok": "1"})},
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
                    {
                        "verify_registration_auth_staging": staticmethod(
                            lambda url, **kwargs: {"anonymous_register": "rejected"}
                        )
                    },
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
                    "ExternalMod",
                    (),
                    {
                        "verify_external_contributor": staticmethod(
                            lambda url, **kwargs: {"task_flow": "ok"}
                        )
                    },
                ),
                type(
                    "AppealMod",
                    (),
                    {"verify_creative_appeal_staging": staticmethod(capture_appeal)},
                ),
            ],
        ),
        patch.object(mod, "_run_pytest") as mock_pytest,
        patch.object(mod.subprocess, "run") as mock_run,
        patch.object(mod, "_env_flag", side_effect=lambda name, default=False: name == "AGENTSWARM_VERIFY_SKIP_NEWS"),
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        result = mod.verify_production_staging(
            "https://theebie.de/agentswarm/api",
            quick=False,
            expect_dispatch=True,
        )

    assert result["mode"] == "full"
    assert result["unit_p7"] == "passed"
    assert result["creative_appeal"]["get_missing_goal"] == "404"
    assert result["news_pipeline"] == "skipped"
    assert result["mcp_adapter"] == "passed"
    assert appeal_calls == ["https://theebie.de/agentswarm/api"]
    assert mock_pytest.call_count == 10
