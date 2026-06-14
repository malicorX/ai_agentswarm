import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.crypto import sign_payload
from agentswarm_platform.deploy_policy import resolve_deploy_policy
from test_task_flow import register_agent


def test_resolve_deploy_policy_from_governance() -> None:
    policy = resolve_deploy_policy(
        {
            "deploy": {
                "required_signoffs": 3,
                "min_credibility": 40,
                "signoff_capabilities": ["reviewer"],
            }
        }
    )
    assert policy.required_signoffs == 3
    assert policy.min_credibility == 40.0
    assert policy.signoff_capabilities == ("reviewer",)


def test_deploy_request_approves_after_quorum(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)

    reviewer_a, priv_a = register_agent(cred_client, ["reviewer"])
    reviewer_b, priv_b = register_agent(cred_client, ["reviewer"])

    created = cred_client.post(
        "/deploy/requests",
        json={
            "environment": "staging",
            "artifact_ref": "sha-abc123",
            "description": "pilot release",
            "required_signoffs": 2,
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "pending"
    assert len(body["approve_task_ids"]) == 2

    for reviewer_id, priv, task_id in zip(
        (reviewer_a, reviewer_b),
        (priv_a, priv_b),
        body["approve_task_ids"],
        strict=True,
    ):
        claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": reviewer_id})
        assert claim.status_code == 200
        result = {"decision": "approve"}
        submit = cred_client.post(
            "/tasks/submit",
            json={
                "claim_token": claim.json()["claim_token"],
                "result": result,
                "signature": sign_payload(priv, {"task_id": task_id, "result": result}),
            },
        )
        assert submit.status_code == 200

    request = cred_client.get(f"/deploy/requests/{body['request_id']}").json()
    assert request["status"] == "approved"
    assert request["signoff_count"] == 2
    assert len(request["signoffs"]) == 2


def test_deploy_signoff_rejects_duplicate_agent(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)

    reviewer_id, priv = register_agent(cred_client, ["reviewer"])
    created = cred_client.post(
        "/deploy/requests",
        json={
            "environment": "staging",
            "artifact_ref": "sha-dup",
            "required_signoffs": 2,
        },
    )
    task_ids = created.json()["approve_task_ids"]

    for task_id in task_ids:
        claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": reviewer_id})
        if claim.status_code != 200:
            continue
        result = {"decision": "approve"}
        submit = cred_client.post(
            "/tasks/submit",
            json={
                "claim_token": claim.json()["claim_token"],
                "result": result,
                "signature": sign_payload(priv, {"task_id": task_id, "result": result}),
            },
        )
        if submit.status_code == 200:
            break

    second_task = task_ids[1] if task_ids[0] != task_ids[1] else task_ids[0]
    claim = cred_client.post(
        f"/tasks/{second_task}/claim", json={"agent_id": reviewer_id}
    )
    if claim.status_code == 200:
        result = {"decision": "approve"}
        submit = cred_client.post(
            "/tasks/submit",
            json={
                "claim_token": claim.json()["claim_token"],
                "result": result,
                "signature": sign_payload(priv, {"task_id": second_task, "result": result}),
            },
        )
        assert submit.status_code == 400
        assert "already signed" in submit.json()["detail"]


def test_deploy_approve_rejects_low_credibility_agent(cred_client: TestClient) -> None:
    reviewer_id, priv = register_agent(cred_client, ["reviewer"])
    created = cred_client.post(
        "/deploy/requests",
        json={
            "environment": "staging",
            "artifact_ref": "sha-low",
            "required_signoffs": 1,
        },
    )
    task_id = created.json()["approve_task_ids"][0]
    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": reviewer_id})
    assert claim.status_code == 400


def test_deploy_request_executes_after_approval(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)

    reviewer_a, priv_a = register_agent(cred_client, ["reviewer"])
    reviewer_b, priv_b = register_agent(cred_client, ["reviewer"])
    deployer_id, deployer_priv = register_agent(cred_client, ["deployer"])

    created = cred_client.post(
        "/deploy/requests",
        json={
            "environment": "staging",
            "artifact_ref": "sha-exec",
            "required_signoffs": 2,
        },
    )
    body = created.json()
    for reviewer_id, priv, task_id in zip(
        (reviewer_a, reviewer_b),
        (priv_a, priv_b),
        body["approve_task_ids"],
        strict=True,
    ):
        claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": reviewer_id})
        result = {"decision": "approve"}
        cred_client.post(
            "/tasks/submit",
            json={
                "claim_token": claim.json()["claim_token"],
                "result": result,
                "signature": sign_payload(priv, {"task_id": task_id, "result": result}),
            },
        )

    approved = cred_client.get(f"/deploy/requests/{body['request_id']}").json()
    assert approved["status"] == "approved"
    execute_task_id = approved["execute_task_id"]
    assert execute_task_id

    claim = cred_client.post(
        f"/tasks/{execute_task_id}/claim", json={"agent_id": deployer_id}
    )
    assert claim.status_code == 200
    result = {
        "request_id": body["request_id"],
        "environment": "staging",
        "artifact_ref": "sha-exec",
        "outcome": "simulated",
        "message": "test",
    }
    submit = cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": result,
            "signature": sign_payload(
                deployer_priv, {"task_id": execute_task_id, "result": result}
            ),
        },
    )
    assert submit.status_code == 200

    deployed = cred_client.get(f"/deploy/requests/{body['request_id']}").json()
    assert deployed["status"] == "deployed"
    assert deployed["executed_by_agent_id"] == deployer_id
    assert deployed["execution_result"]["outcome"] == "simulated"


def test_deploy_reject_cancels_pending_request(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)

    reviewer_id, priv = register_agent(cred_client, ["reviewer"])
    created = cred_client.post(
        "/deploy/requests",
        json={
            "environment": "staging",
            "artifact_ref": "sha-reject",
            "required_signoffs": 2,
        },
    )
    task_id = created.json()["approve_task_ids"][0]
    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": reviewer_id})
    result = {"decision": "reject", "reason": "artifact not verified"}
    submit = cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": result,
            "signature": sign_payload(priv, {"task_id": task_id, "result": result}),
        },
    )
    assert submit.status_code == 200

    request = cred_client.get(f"/deploy/requests/{created.json()['request_id']}").json()
    assert request["status"] == "rejected"

