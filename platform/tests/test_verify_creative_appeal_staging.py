from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_creative_appeal_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_creative_appeal_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_creative_appeal_staging_probes_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "test-bootstrap")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    missing = MagicMock(status_code=404)
    appeal = MagicMock(status_code=400, text="goal not found")
    resolve = MagicMock(status_code=400, text="goal not found")
    mock_client.get.return_value = missing
    mock_client.post.side_effect = [appeal, resolve]

    with patch.object(httpx, "Client", return_value=mock_client):
        result = mod.verify_creative_appeal_staging("https://theebie.de/agentswarm/api")

    assert result["get_missing_goal"] == "404"
    assert result["post_appeal_missing_goal"] == "400"
    assert result["post_resolve_missing_goal"] == "400"
    assert mock_client.post.call_count == 2
