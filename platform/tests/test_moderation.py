from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload
from test_task_flow import register_agent


def test_moderator_quarantines_high_canary_failure_agent(client: TestClient) -> None:
    bad_id, bad_priv = register_agent(client, ["classifier"])
    mod_id, mod_priv = register_agent(client, ["moderator"])

    for label in ("tech", "politics"):
        create = client.post(
            "/tasks",
            json={
                "task_type": "classifier.label",
                "capability_required": "classifier",
                "payload": {
                    "text": "canary probe",
                    "labels": ["tech", "politics"],
                    "replication": False,
                    "canary": {"expected": {"label": "tech"}},
                },
            },
        )
        task_id = create.json()["task_id"]
        claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": bad_id})
        signature = sign_payload(
            bad_priv,
            {"task_id": task_id, "result": {"label": label}},
        )
        client.post(
            "/tasks/submit",
            json={
                "claim_token": claim.json()["claim_token"],
                "result": {"label": label},
                "signature": signature,
            },
        )

    scan = client.post(
        "/tasks",
        json={
            "task_type": "moderator.scan",
            "capability_required": "moderator",
            "payload": {},
        },
    )
    task_id = scan.json()["task_id"]
    claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": mod_id})
    result = {
        "findings": [{"type": "canary_failure_rate", "agent_id": bad_id}],
        "actions": [
            {
                "type": "quarantine",
                "agent_id": bad_id,
                "reason": "test quarantine",
            }
        ],
    }
    signature = sign_payload(mod_priv, {"task_id": task_id, "result": result})
    submit = client.post(
        "/tasks/submit",
        json={"claim_token": claim.json()["claim_token"], "result": result, "signature": signature},
    )
    assert submit.status_code == 200

    agent = client.get(f"/agents/{bad_id}").json()
    assert agent["quarantined"] is True

    flags = client.get("/moderation/flags").json()
    assert any(f["subject_id"] == bad_id for f in flags["flags"])

    blocked = client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {},
        },
    )
    writer_id, _ = register_agent(client, ["codewriter"])
    blocked_claim = client.post(
        f"/tasks/{blocked.json()['task_id']}/claim",
        json={"agent_id": bad_id},
    )
    assert blocked_claim.status_code == 403
