from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_hardware_gates_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_hardware_gates_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_hardware_gates_staging_rejects_low_vram_when_enforced() -> None:
    mod = _load_module()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    config_resp = MagicMock()
    config_resp.raise_for_status = MagicMock()
    config_resp.json.return_value = {
        "auth": {"enforced": False},
        "hardware": {"enforced": True, "reviewer_min_vram_gb": 6.0},
    }
    reg_resp = MagicMock()
    reg_resp.raise_for_status = MagicMock()
    reg_resp.json.return_value = {"agent_id": "agent-hw"}
    missing_resp = MagicMock(status_code=400)
    low_resp = MagicMock(status_code=400)
    ok_resp = MagicMock()
    ok_resp.raise_for_status = MagicMock()

    mock_client.get.return_value = config_resp
    mock_client.post.side_effect = [reg_resp, missing_resp, low_resp, ok_resp]

    with patch.object(httpx, "Client", return_value=mock_client):
        result = mod.verify_hardware_gates_staging(
            "https://theebie.de/agentswarm/api",
            expect_enforced=True,
        )

    assert result["low_vram_rejected"] == "ok"
