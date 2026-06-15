from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_external_contributor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_external_contributor", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_external_contributor_identity_and_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()
    poll_resp = MagicMock()
    poll_resp.json.return_value = []
    poll_resp.raise_for_status = MagicMock()
    mock_client.get.side_effect = [health_resp, poll_resp]

    identity = MagicMock()
    identity.agent_id = "agent_external"
    with (
        patch.object(httpx, "Client", return_value=mock_client),
        patch.object(mod, "connect_agent", return_value=identity) as connect,
        patch.object(mod, "load_identity") as load_identity,
    ):
        load_identity.return_value = MagicMock(agent_id="agent_external")
        result = mod.verify_external_contributor(
            "https://theebie.de/agentswarm/api",
            repo_root=REPO_ROOT,
            identity_dir=REPO_ROOT / ".tmp-test-identity",
            run_task_flow=False,
        )

    assert result["health"] == "ok"
    assert result["identity_persistence"] == "ok"
    assert result["poll"] == "ok"
    assert result["task_flow"] == "skipped"
    assert connect.call_count == 2


def test_verify_external_contributor_skips_task_without_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.delenv("AGENTSWARM_BOOTSTRAP_TOKEN", raising=False)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()
    poll_resp = MagicMock()
    poll_resp.json.return_value = []
    poll_resp.raise_for_status = MagicMock()
    mock_client.get.side_effect = [health_resp, poll_resp]

    identity = MagicMock()
    identity.agent_id = "agent_external"
    with (
        patch.object(httpx, "Client", return_value=mock_client),
        patch.object(mod, "connect_agent", return_value=identity),
        patch.object(mod, "load_identity", return_value=MagicMock(agent_id="agent_external")),
    ):
        result = mod.verify_external_contributor(
            "https://theebie.de/agentswarm/api",
            repo_root=REPO_ROOT,
            identity_dir=REPO_ROOT / ".tmp-test-identity",
            run_task_flow=True,
            bootstrap_token="",
        )

    assert result["task_flow"] == "skipped_no_bootstrap"
