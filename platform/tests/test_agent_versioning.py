from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.agent_versioning import (
    classify_version_bump,
    parse_version_signature,
)
from agentswarm_platform.crypto import generate_keypair, public_key_b64


def test_parse_version_signature() -> None:
    parsed = parse_version_signature("codewriter-v2.1")
    assert parsed.family == "codewriter"
    assert parsed.major == 2
    assert parsed.minor == 1


def test_classify_version_bump() -> None:
    assert classify_version_bump("codewriter-v1.0", "codewriter-v1.0") is None
    assert classify_version_bump("codewriter-v1.0", "codewriter-v1.1") == "minor"
    assert classify_version_bump("codewriter-v1.9", "codewriter-v2.0") == "major"


def test_is_version_downgrade() -> None:
    from agentswarm_platform.agent_versioning import is_version_downgrade

    assert is_version_downgrade("codewriter-v2.0", "codewriter-v1.9") is True
    assert is_version_downgrade("codewriter-v1.1", "codewriter-v1.0") is True
    assert is_version_downgrade("codewriter-v1.0", "codewriter-v1.1") is False
    assert is_version_downgrade("codewriter-v1.0", "reviewer-v1.0") is False


def test_reconnect_rejects_version_downgrade(client: TestClient) -> None:
    pub, _priv = generate_keypair()
    body = {
        "public_key": public_key_b64(pub),
        "owner": "version-downgrade",
        "capabilities": ["reviewer"],
        "version_signature": "reviewer-v2.0",
    }
    first = client.post("/agents/register", json=body)
    assert first.status_code == 200

    body["version_signature"] = "reviewer-v1.9"
    second = client.post("/agents/register", json=body)
    assert second.status_code == 400
    assert "downgrade" in second.json()["detail"].lower()

    agent = client.get(f"/agents/{first.json()['agent_id']}").json()
    assert agent["version_signature"] == "reviewer-v2.0"


def test_downgrade_allowed_when_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENTSWARM_VERSION_REJECT_DOWNGRADES", "0")
    pub, _priv = generate_keypair()
    body = {
        "public_key": public_key_b64(pub),
        "owner": "version-downgrade-off",
        "capabilities": ["reviewer"],
        "version_signature": "reviewer-v2.0",
    }
    client.post("/agents/register", json=body)
    body["version_signature"] = "reviewer-v1.9"
    second = client.post("/agents/register", json=body)
    assert second.status_code == 200


def test_register_rejects_invalid_version(client: TestClient) -> None:
    pub, _priv = generate_keypair()
    response = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "version-test",
            "capabilities": ["reviewer"],
            "version_signature": "bad",
        },
    )
    assert response.status_code == 400


def test_version_history_on_bump(client: TestClient) -> None:
    pub, _priv = generate_keypair()
    body = {
        "public_key": public_key_b64(pub),
        "owner": "version-history",
        "capabilities": ["reviewer"],
        "version_signature": "reviewer-v1.0",
    }
    first = client.post("/agents/register", json=body)
    assert first.status_code == 200
    agent_id = first.json()["agent_id"]

    versions = client.get(f"/agents/{agent_id}/versions").json()["versions"]
    assert len(versions) == 1
    assert versions[0]["bump_kind"] == "initial"

    body["version_signature"] = "reviewer-v1.1"
    second = client.post("/agents/register", json=body)
    assert second.status_code == 200
    versions = client.get(f"/agents/{agent_id}/versions").json()["versions"]
    assert len(versions) == 2
    assert versions[-1]["bump_kind"] == "minor"
    assert versions[-1]["previous_version"] == "reviewer-v1.0"

    body["version_signature"] = "reviewer-v2.0"
    third = client.post("/agents/register", json=body)
    assert third.status_code == 200
    versions = client.get(f"/agents/{agent_id}/versions").json()["versions"]
    assert len(versions) == 3
    assert versions[-1]["bump_kind"] == "major"


def test_major_bump_haircuts_credibility(cred_client: TestClient) -> None:
    pub, _priv = generate_keypair()
    body = {
        "public_key": public_key_b64(pub),
        "owner": "version-haircut",
        "capabilities": ["reviewer"],
        "version_signature": "reviewer-v1.0",
    }
    reg = cred_client.post("/agents/register", json=body)
    agent_id = reg.json()["agent_id"]

    import agentswarm_platform.main as main_module

    with main_module.store._conn() as conn:
        from agentswarm_platform.credibility_ledger import _apply_delta

        _apply_delta(
            conn,
            agent_id=agent_id,
            capability="reviewer",
            project_id="default",
            delta=20.0,
            reason="test.seed",
            ref_type="test",
            ref_id="test",
            details={},
            apply_decay_before=False,
        )

    before = cred_client.get(f"/agents/{agent_id}/credibility").json()
    score_before = before["capabilities"][0]["score"]
    assert score_before == pytest.approx(30.0)

    body["version_signature"] = "reviewer-v2.0"
    cred_client.post("/agents/register", json=body)
    after = cred_client.get(f"/agents/{agent_id}/credibility").json()
    score_after = after["capabilities"][0]["score"]
    assert score_after == pytest.approx(20.0)
