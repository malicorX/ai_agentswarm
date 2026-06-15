from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_agent_versioning_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_agent_versioning_staging", VERIFY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_agent_versioning_staging_minor_and_major(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    agent_id = "agent_test"
    version_lists = [
        [{"bump_kind": "initial", "version_signature": "reviewer-v1.0"}],
        [
            {"bump_kind": "initial", "version_signature": "reviewer-v1.0"},
            {
                "bump_kind": "minor",
                "version_signature": "reviewer-v1.1",
                "previous_version": "reviewer-v1.0",
            },
        ],
        [
            {"bump_kind": "initial", "version_signature": "reviewer-v1.0"},
            {
                "bump_kind": "minor",
                "version_signature": "reviewer-v1.1",
                "previous_version": "reviewer-v1.0",
            },
            {"bump_kind": "major", "version_signature": "reviewer-v2.0"},
        ],
    ]
    call_index = {"n": 0}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()
    mock_client.get.side_effect = [health_resp] + [
        MagicMock(
            json=MagicMock(return_value={"versions": version_lists[i]}),
            raise_for_status=MagicMock(),
        )
        for i in range(3)
    ]

    clients = [
        MagicMock(agent_id=agent_id),
        MagicMock(agent_id=agent_id),
        MagicMock(agent_id=agent_id),
    ]

    def fake_connect(**_kwargs):
        client = clients[call_index["n"]]
        call_index["n"] += 1
        return client

    monkeypatch.setenv("AGENTSWARM_VERSION_VERIFY_IDENTITY_DIR", "/tmp/agentswarm-version-verify-test")
    with (
        patch.object(httpx, "Client", return_value=mock_client),
        patch.object(mod, "connect_agent", side_effect=fake_connect),
    ):
        result = mod.verify_agent_versioning_staging("https://theebie.de/agentswarm/api")

    assert result["agent_id"] == agent_id
    assert result["minor_bump"] == "reviewer-v1.1"
    assert result["major_bump"] == "reviewer-v2.0"
    assert call_index["n"] == 3
