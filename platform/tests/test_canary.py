from fastapi.testclient import TestClient

from agentswarm_platform.canary import canary_passes


def test_canary_passes_when_label_matches() -> None:
    assert canary_passes(
        "classifier.label",
        {"label": "tech"},
        {"label": "tech"},
    )


def test_canary_fails_when_label_differs() -> None:
    assert not canary_passes(
        "classifier.label",
        {"label": "tech"},
        {"label": "politics"},
    )


def test_canary_task_records_failure(client: TestClient) -> None:
    from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload

    pub, priv = generate_keypair()
    reg = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "canary-tester",
            "capabilities": ["classifier"],
        },
    )
    agent_id = reg.json()["agent_id"]

    create = client.post(
        "/tasks",
        json={
            "task_type": "classifier.label",
            "capability_required": "classifier",
            "payload": {
                "text": "hidden canary",
                "labels": ["tech", "politics"],
                "replication": False,
                "canary": {"expected": {"label": "tech"}},
            },
        },
    )
    task_id = create.json()["task_id"]
    claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": agent_id})
    result = {"label": "politics"}
    signature = sign_payload(priv, {"task_id": task_id, "result": result})
    submit = client.post(
        "/tasks/submit",
        json={"claim_token": claim.json()["claim_token"], "result": result, "signature": signature},
    )
    assert submit.status_code == 200
    assert submit.json()["canary_passed"] is False

    stats = client.get(f"/agents/{agent_id}/canary-stats").json()
    assert stats["attempts"] == 1
    assert stats["failures"] == 1
