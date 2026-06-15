from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_production_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_production_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_production_staging_full_runs_mcp_adapter() -> None:
    mod = _load_module()
    mcp_calls: list[list[str]] = []

    def capture_mcp(cmd: list[str], **kwargs: object) -> MagicMock:
        mcp_calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    modules = [
        type(
            "PlatformMod",
            (),
            {
                "verify_production_platform": staticmethod(
                    lambda url, **kwargs: {
                        "health": "ok",
                        "assignment_mode": "pull",
                    }
                )
            },
        ),
        type("VersionMod", (), {"verify_agent_versioning_staging": staticmethod(lambda url: {})}),
        type(
            "CredMod",
            (),
            {"verify_credibility_staging": staticmethod(lambda url, **kwargs: {})},
        ),
        type(
            "RegAuthMod",
            (),
            {"verify_registration_auth_staging": staticmethod(lambda url, **kwargs: {})},
        ),
        type(
            "ModelMod",
            (),
            {"verify_model_allowlist_staging": staticmethod(lambda url, **kwargs: {})},
        ),
        type(
            "HardwareMod",
            (),
            {"verify_hardware_gates_staging": staticmethod(lambda url, **kwargs: {})},
        ),
        type(
            "ExternalMod",
            (),
            {"verify_external_contributor": staticmethod(lambda url, **kwargs: {})},
        ),
    ]

    def env_flag(name: str, default: bool = False) -> bool:
        if name == "AGENTSWARM_VERIFY_SKIP_NEWS":
            return True
        if name == "AGENTSWARM_VERIFY_SKIP_MCP":
            return False
        return default

    with (
        patch.object(mod, "_load_script_module", side_effect=modules),
        patch.object(mod, "_run_pytest"),
        patch.object(mod, "_env_flag", side_effect=env_flag),
        patch.object(mod.subprocess, "run", side_effect=capture_mcp),
        patch.dict(os.environ, {}, clear=False),
    ):
        result = mod.verify_production_staging(
            "https://theebie.de/agentswarm/api",
            quick=False,
        )

    assert result["mcp_adapter"] == "passed"
    assert len(mcp_calls) == 1
    assert mcp_calls[0][-1].endswith("verify_mcp_adapter.py")
