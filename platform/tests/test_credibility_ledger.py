from fastapi.testclient import TestClient

from agentswarm_platform.credibility import INITIAL_SCORE
from test_task_flow import register_agent


def test_credibility_after_full_task_flow(cred_client: TestClient) -> None:
    writer_id, writer_priv = register_agent(cred_client, ["codewriter"])
    tester_id, tester_priv = register_agent(cred_client, ["tester"])
    reviewer_id, reviewer_priv = register_agent(cred_client, ["reviewer"])

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "stake_tier": "low"},
        },
    )
    assert create.status_code == 200
    task_id = create.json()["task_id"]

    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    assert claim.status_code == 200
    claim_token = claim.json()["claim_token"]

    from agentswarm_platform.crypto import sign_payload

    result = {"file": "index.html", "applied": True}
    signature = sign_payload(writer_priv, {"task_id": task_id, "result": result})
    submit = cred_client.post(
        "/tasks/submit",
        json={"claim_token": claim_token, "result": result, "signature": signature},
    )
    assert submit.status_code == 200

    tester_tasks = cred_client.get(
        "/tasks/poll", params={"agent_id": tester_id, "capability": "tester"}
    ).json()
    tester_task_id = tester_tasks[0]["task_id"]
    tester_claim = cred_client.post(
        f"/tasks/{tester_task_id}/claim", json={"agent_id": tester_id}
    )
    tester_token = tester_claim.json()["claim_token"]
    test_result = {"passed": True, "tests_run": 1}
    tester_sig = sign_payload(
        tester_priv, {"task_id": tester_task_id, "result": test_result}
    )
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": tester_token,
            "result": test_result,
            "signature": tester_sig,
        },
    )

    reviewer_tasks = cred_client.get(
        "/tasks/poll", params={"agent_id": reviewer_id, "capability": "reviewer"}
    ).json()
    reviewer_task_id = reviewer_tasks[0]["task_id"]
    reviewer_claim = cred_client.post(
        f"/tasks/{reviewer_task_id}/claim", json={"agent_id": reviewer_id}
    )
    reviewer_token = reviewer_claim.json()["claim_token"]
    review_result = {"approved": True, "notes": "looks good"}
    reviewer_sig = sign_payload(
        reviewer_priv, {"task_id": reviewer_task_id, "result": review_result}
    )
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": reviewer_token,
            "result": review_result,
            "signature": reviewer_sig,
        },
    )

    writer_cred = cred_client.get(f"/agents/{writer_id}/credibility").json()
    writer_score = next(
        c["score"] for c in writer_cred["capabilities"] if c["capability"] == "codewriter"
    )
    assert writer_score > INITIAL_SCORE

    reviewer_cred = cred_client.get(f"/agents/{reviewer_id}/credibility").json()
    reviewer_score = next(
        c["score"]
        for c in reviewer_cred["capabilities"]
        if c["capability"] == "reviewer"
    )
    assert reviewer_score > INITIAL_SCORE

    board = cred_client.get(
        "/credibility/leaderboard", params={"capability": "codewriter"}
    ).json()
    assert any(entry["agent_id"] == writer_id for entry in board["entries"])


def test_leaderboard_empty_when_credibility_disabled(client: TestClient) -> None:
    response = client.get("/credibility/leaderboard")
    assert response.status_code == 200
    assert response.json()["entries"] == []
