"""Tests for persistent agent identity."""

import pytest

from agentswarm_agents.identity import StoredIdentity, load_identity, save_identity


def test_save_and_load_identity(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path))
    identity = StoredIdentity(
        agent_name="tester",
        agent_id="agent_abc",
        public_key_b64="cHVi",
        private_key_b64="cHJp",
        owner="owner",
        capabilities=["tester"],
    )
    save_identity(identity)
    loaded = load_identity("tester")
    assert loaded is not None
    assert loaded.agent_id == "agent_abc"
    assert loaded.capabilities == ["tester"]
