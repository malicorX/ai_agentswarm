from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload
from test_task_flow import register_agent


def _register_classifiers(client: TestClient, count: int) -> list[tuple[str, bytes]]:
    agents: list[tuple[str, bytes]] = []
    for i in range(count):
        pub, priv = generate_keypair()
        response = client.post(
            "/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"classifier-{i}",
                "capabilities": ["classifier"],
            },
        )
        assert response.status_code == 200
        agents.append((response.json()["agent_id"], priv))
    return agents


def _submit_label(
    client: TestClient,
    claim_token: str,
    task_id: str,
    priv: bytes,
    label: str,
) -> dict:
    result = {"label": label}
    signature = sign_payload(priv, {"task_id": task_id, "result": result})
    response = client.post(
        "/tasks/submit",
        json={"claim_token": claim_token, "result": result, "signature": signature},
    )
    assert response.status_code == 200
    return response.json()


def test_replication_quorum_met(client: TestClient) -> None:
    agents = _register_classifiers(client, 2)
    create = client.post(
        "/tasks",
        json={
            "task_type": "classifier.label",
            "capability_required": "classifier",
            "payload": {
                "text": "New AI chip announced",
                "labels": ["tech", "politics", "sports"],
                "replication": {"slots": 3, "quorum": 2},
            },
        },
    )
    assert create.status_code == 200
    group_id = create.json()["payload"]["replication_group_id"]

    submissions = []
    for i, (agent_id, priv) in enumerate(agents):
        tasks = client.get(
            "/tasks/poll", params={"agent_id": agent_id, "capability": "classifier"}
        ).json()
        assert len(tasks) >= 1
        task_id = tasks[0]["task_id"]
        claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": agent_id})
        assert claim.status_code == 200
        label = "tech"
        body = _submit_label(
            client, claim.json()["claim_token"], task_id, priv, label
        )
        submissions.append(body)

    assert submissions[1]["replication_status"] == "quorum_met"

    group = client.get(f"/replication/{group_id}").json()
    assert group["status"] == "quorum_met"
    assert group["winning_result"] == {"label": "tech"}


def test_replication_disputed(client: TestClient) -> None:
    agents = _register_classifiers(client, 3)
    create = client.post(
        "/tasks",
        json={
            "task_type": "classifier.label",
            "capability_required": "classifier",
            "payload": {
                "text": "Election tech policy",
                "labels": ["tech", "politics", "sports"],
            },
        },
    )
    group_id = create.json()["payload"]["replication_group_id"]
    labels = ["tech", "politics", "sports"]

    for i, ((agent_id, priv), label) in enumerate(zip(agents, labels, strict=True)):
        tasks = client.get(
            "/tasks/poll", params={"agent_id": agent_id, "capability": "classifier"}
        ).json()
        task_id = tasks[0]["task_id"]
        claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": agent_id})
        _submit_label(client, claim.json()["claim_token"], task_id, priv, label)

    group = client.get(f"/replication/{group_id}").json()
    assert group["status"] == "disputed"
    assert group["winning_result"] is None


def test_agent_cannot_claim_two_slots(client: TestClient) -> None:
    agent_id, _priv = _register_classifiers(client, 1)[0]
    client.post(
        "/tasks",
        json={
            "task_type": "classifier.label",
            "capability_required": "classifier",
            "payload": {"text": "sample", "labels": ["tech", "politics"]},
        },
    )
    tasks = client.get(
        "/tasks/poll", params={"agent_id": agent_id, "capability": "classifier"}
    ).json()
    assert len(tasks) == 3
    first = client.post(
        f"/tasks/{tasks[0]['task_id']}/claim", json={"agent_id": agent_id}
    )
    assert first.status_code == 200
    second = client.post(
        f"/tasks/{tasks[1]['task_id']}/claim", json={"agent_id": agent_id}
    )
    assert second.status_code == 400
