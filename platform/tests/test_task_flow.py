import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload
from agentswarm_platform.main import app
from agentswarm_platform.store import Store


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.main as main_module

        main_module.store = Store(db_path)
        yield TestClient(main_module.app)


def register_agent(
    client: TestClient, capabilities: list[str], owner: str = "test-owner"
) -> tuple[str, bytes]:
    pub_raw, priv_raw = generate_keypair()
    response = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub_raw),
            "owner": owner,
            "capabilities": capabilities,
        },
    )
    assert response.status_code == 200
    agent_id = response.json()["agent_id"]
    return agent_id, priv_raw


def test_task_lifecycle_codewriter_to_verified(client: TestClient) -> None:
    writer_id, writer_priv = register_agent(client, ["codewriter"])
    tester_id, tester_priv = register_agent(client, ["tester"])
    reviewer_id, reviewer_priv = register_agent(client, ["reviewer"])

    create = client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "content": "<!-- patched -->"},
        },
    )
    assert create.status_code == 200
    task_id = create.json()["task_id"]

    claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    assert claim.status_code == 200
    claim_token = claim.json()["claim_token"]

    result = {"file": "index.html", "applied": True}
    signature = sign_payload(writer_priv, {"task_id": task_id, "result": result})
    submit = client.post(
        "/tasks/submit",
        json={"claim_token": claim_token, "result": result, "signature": signature},
    )
    assert submit.status_code == 200

    tester_tasks = client.get(
        "/tasks/poll", params={"agent_id": tester_id, "capability": "tester"}
    ).json()
    assert len(tester_tasks) == 1
    tester_task_id = tester_tasks[0]["task_id"]

    tester_claim = client.post(
        f"/tasks/{tester_task_id}/claim", json={"agent_id": tester_id}
    )
    tester_token = tester_claim.json()["claim_token"]
    test_result = {"passed": True, "tests_run": 1}
    tester_sig = sign_payload(
        tester_priv, {"task_id": tester_task_id, "result": test_result}
    )
    client.post(
        "/tasks/submit",
        json={
            "claim_token": tester_token,
            "result": test_result,
            "signature": tester_sig,
        },
    )

    reviewer_tasks = client.get(
        "/tasks/poll", params={"agent_id": reviewer_id, "capability": "reviewer"}
    ).json()
    assert len(reviewer_tasks) == 1
    reviewer_task_id = reviewer_tasks[0]["task_id"]

    reviewer_claim = client.post(
        f"/tasks/{reviewer_task_id}/claim", json={"agent_id": reviewer_id}
    )
    reviewer_token = reviewer_claim.json()["claim_token"]
    review_result = {"approved": True, "notes": "looks good"}
    reviewer_sig = sign_payload(
        reviewer_priv, {"task_id": reviewer_task_id, "result": review_result}
    )
    client.post(
        "/tasks/submit",
        json={
            "claim_token": reviewer_token,
            "result": review_result,
            "signature": reviewer_sig,
        },
    )

    parent = client.get(f"/tasks/{task_id}").json()
    assert parent["status"] == "verified"

    audit = client.get("/audit").json()
    event_types = [e["event_type"] for e in audit]
    assert "task.created" in event_types
    assert "task.submitted" in event_types
    assert "task.verified" in event_types


def test_register_idempotent_by_public_key(client: TestClient) -> None:
    pub_raw, _priv_raw = generate_keypair()
    pub = public_key_b64(pub_raw)
    body = {
        "public_key": pub,
        "owner": "alice",
        "capabilities": ["codewriter"],
    }
    first = client.post("/agents/register", json=body)
    second = client.post("/agents/register", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["agent_id"] == second.json()["agent_id"]

    audit = client.get("/audit").json()
    assert any(e["event_type"] == "agent.reconnected" for e in audit)


def test_invalid_signature_rejected(client: TestClient) -> None:
    writer_id, _writer_priv = register_agent(client, ["codewriter"])
    create = client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {},
        },
    )
    task_id = create.json()["task_id"]
    claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    claim_token = claim.json()["claim_token"]
    submit = client.post(
        "/tasks/submit",
        json={
            "claim_token": claim_token,
            "result": {"ok": True},
            "signature": "invalid-signature",
        },
    )
    assert submit.status_code == 400
