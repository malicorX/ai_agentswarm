from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_lease_reclaim_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_lease_reclaim_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_auth_headers_requires_bootstrap_when_auth_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.delenv("AGENTSWARM_BOOTSTRAP_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="AGENTSWARM_BOOTSTRAP_TOKEN"):
        mod._auth_headers({"auth": {"enforced": True}})


def test_verify_lease_reclaim_staging_happy_path(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "test-bootstrap")
    monkeypatch.setattr(mod.time, "sleep", lambda _sec: None)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    config_resp = MagicMock()
    config_resp.raise_for_status = MagicMock()
    config_resp.json.return_value = {
        "assignment_mode": "dispatch",
        "auth": {"enforced": True},
        "dispatch": {"lease_ttl_minutes": 60},
        "hardware": {"enforced": False},
    }
    reg_a = MagicMock()
    reg_a.raise_for_status = MagicMock()
    reg_a.json.return_value = {"agent_id": "agent-a"}
    reg_b = MagicMock()
    reg_b.raise_for_status = MagicMock()
    reg_b.json.return_value = {"agent_id": "agent-b"}
    need_ok = MagicMock()
    need_ok.raise_for_status = MagicMock()
    need_ok.json.return_value = {"assigned": True, "task_id": "task-lease-1"}
    presence_ok = MagicMock()
    presence_ok.raise_for_status = MagicMock()
    pending_a = MagicMock()
    pending_a.json.return_value = {"task_id": "task-lease-1"}
    pending_a2 = MagicMock()
    pending_a2.json.return_value = None
    pending_b = MagicMock()
    pending_b.json.return_value = {"task_id": "task-lease-1"}
    released_a = MagicMock()
    released_a.json.return_value = None

    mock_client.get.side_effect = [
        config_resp,
        pending_a,
        pending_a2,
        pending_a2,
        pending_b,
        released_a,
    ]
    mock_client.post.side_effect = [
        reg_a,
        reg_b,
        presence_ok,
        need_ok,
        presence_ok,
    ]

    with patch.object(httpx, "Client", return_value=mock_client):
        result = mod.verify_lease_reclaim_staging(
            "https://theebie.de/agentswarm/api",
            stale_wait_sec=0,
        )

    assert result["stale_reclaim"] == "ok"
    assert result["task_id"] == "task-lease-1"
