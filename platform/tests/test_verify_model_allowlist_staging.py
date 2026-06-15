from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_model_allowlist_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_model_allowlist_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_model_allowlist_staging_rejects_unknown_when_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "test-bootstrap")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    config_resp = MagicMock()
    config_resp.raise_for_status = MagicMock()
    config_resp.json.return_value = {
        "auth": {"enforced": True},
        "models": {
            "enforced": True,
            "allowlist": [{"id": "llm-mock-v1"}],
        },
    }
    reg_resp = MagicMock()
    reg_resp.raise_for_status = MagicMock()
    reg_resp.json.return_value = {"agent_id": "agent-model"}
    bad_resp = MagicMock(status_code=400, text="not on allowlist")
    good_resp = MagicMock()
    good_resp.raise_for_status = MagicMock()

    mock_client.get.return_value = config_resp
    mock_client.post.side_effect = [reg_resp, bad_resp, good_resp]

    with patch.object(httpx, "Client", return_value=mock_client):
        result = mod.verify_model_allowlist_staging(
            "https://theebie.de/agentswarm/api",
            expect_enforced=True,
        )

    assert result["unknown_model_presence"] == "rejected"
    assert result["allowed_model_presence"] == "ok"
