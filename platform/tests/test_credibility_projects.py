from fastapi.testclient import TestClient

import agentswarm_platform.credibility as credibility
from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload
from test_task_flow import register_agent


def _complete_codewriter_flow(
    client: TestClient,
    writer_id: str,
    writer_priv,
    tester_id: str,
    tester_priv,
    reviewer_id: str,
    reviewer_priv,
    task_id: str,
) -> None:
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


def test_per_project_credibility_isolated(cred_client: TestClient) -> None:
    cred_client.post(
        "/projects",
        json={"project_id": "news-hub", "name": "AI News Hub"},
    )

    pub, priv = generate_keypair()
    writer_id = cred_client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "alice",
            "capabilities": ["codewriter"],
            "project_ids": ["news-hub"],
        },
    ).json()["agent_id"]

    tester_id, tester_priv = register_agent(cred_client, ["tester"], project_ids=["news-hub"])
    reviewer_id, reviewer_priv = register_agent(cred_client, ["reviewer"], project_ids=["news-hub"])

    hub_task = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "hub.html", "stake_tier": "low"},
            "project_id": "news-hub",
        },
    ).json()["task_id"]

    default_task = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "default.html", "stake_tier": "low"},
        },
    ).json()["task_id"]

    default_writer_id, default_writer_priv = register_agent(cred_client, ["codewriter"])
    default_tester_id, default_tester_priv = register_agent(cred_client, ["tester"])
    default_reviewer_id, default_reviewer_priv = register_agent(cred_client, ["reviewer"])

    _complete_codewriter_flow(
        cred_client,
        writer_id,
        priv,
        tester_id,
        tester_priv,
        reviewer_id,
        reviewer_priv,
        hub_task,
    )
    _complete_codewriter_flow(
        cred_client,
        default_writer_id,
        default_writer_priv,
        default_tester_id,
        default_tester_priv,
        default_reviewer_id,
        default_reviewer_priv,
        default_task,
    )

    hub_score = cred_client.get(
        f"/agents/{writer_id}/credibility", params={"project_id": "news-hub"}
    ).json()
    hub_writer = next(
        c for c in hub_score["capabilities"] if c["capability"] == "codewriter"
    )
    assert hub_writer["score"] > credibility.INITIAL_SCORE

    default_only = cred_client.get(
        f"/agents/{writer_id}/credibility", params={"project_id": "default"}
    ).json()
    assert default_only["capabilities"] == []

    board_hub = cred_client.get(
        "/credibility/leaderboard",
        params={"capability": "codewriter", "project_id": "news-hub"},
    ).json()
    assert any(entry["agent_id"] == writer_id for entry in board_hub["entries"])
    assert board_hub["project_id"] == "news-hub"

    board_default = cred_client.get(
        "/credibility/leaderboard",
        params={"capability": "codewriter", "project_id": "default"},
    ).json()
    assert all(entry["agent_id"] != writer_id for entry in board_default["entries"])
