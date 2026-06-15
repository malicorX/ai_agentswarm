from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_production_platform.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_production_platform", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_production_platform_register_smoke() -> None:
    mod = _load_module()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()
    config_resp = MagicMock()
    config_resp.json.return_value = {"assignment_mode": "dispatch"}
    config_resp.raise_for_status = MagicMock()
    reg_resp = MagicMock()
    reg_resp.json.return_value = {"agent_id": "agent_test"}
    reg_resp.raise_for_status = MagicMock()
    mock_client.get.side_effect = [health_resp, config_resp]
    mock_client.post.return_value = reg_resp

    with patch.object(httpx, "Client", return_value=mock_client):
        result = mod.verify_production_platform(
            "https://theebie.de/agentswarm/api",
            expect_dispatch=True,
        )

    assert result["health"] == "ok"
    assert result["assignment_mode"] == "dispatch"
    assert result["register"] == "agent_test"
    mock_client.post.assert_called_once()
