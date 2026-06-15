from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_production_swarm.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_production_swarm", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_production_swarm_waits_for_verified_count(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "test-bootstrap")

    summaries = [
        {"tasks": {"verified": 1}},
        {"tasks": {"verified": 2}},
    ]

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    enqueue_resp = MagicMock()
    enqueue_resp.json.return_value = {"task_id": "task_abc"}
    enqueue_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = enqueue_resp

    def _get(url: str) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = summaries.pop(0) if summaries else {"tasks": {"verified": 2}}
        return resp

    mock_client.get.side_effect = _get

    with patch.object(httpx, "Client", return_value=mock_client):
        with patch.object(mod.time, "sleep"):
            result = mod.verify_production_swarm(
                "https://theebie.de/agentswarm/api",
                timeout_sec=5.0,
                poll_sec=0.01,
            )

    assert result["task_id"] == "task_abc"
    assert result["verified_after"] == 2
