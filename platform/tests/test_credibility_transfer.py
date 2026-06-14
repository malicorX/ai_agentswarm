import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.credibility import INITIAL_SCORE
from agentswarm_platform.credibility_transfer import (
    CROSS_PROJECT_HAIRCUT,
    compute_imported_score,
)
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


def test_compute_imported_score_applies_haircut_to_earned_portion() -> None:
    source_score = INITIAL_SCORE + 8.0
    imported = compute_imported_score(source_score, haircut=0.5)
    assert imported == pytest.approx(INITIAL_SCORE + 4.0)


def test_compute_imported_score_never_below_initial() -> None:
    assert compute_imported_score(INITIAL_SCORE - 2) == pytest.approx(INITIAL_SCORE)


def test_transfer_rules_endpoint(cred_client: TestClient) -> None:
    response = cred_client.get("/credibility/transfer-rules")
    assert response.status_code == 200
    body = response.json()
    assert body["haircut_rate"] == CROSS_PROJECT_HAIRCUT
    assert body["initial_score"] == INITIAL_SCORE


def test_import_credibility_into_new_project(cred_client: TestClient) -> None:
    cred_client.post(
        "/projects",
        json={"project_id": "news-hub", "name": "AI News Hub"},
    )

    pub, priv = generate_keypair()
    writer_id = cred_client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "test-owner",
            "capabilities": ["codewriter"],
        },
    ).json()["agent_id"]

    tester_id, tester_priv = register_agent(cred_client, ["tester"])
    reviewer_id, reviewer_priv = register_agent(cred_client, ["reviewer"])

    task_id = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "stake_tier": "low"},
        },
    ).json()["task_id"]

    _complete_codewriter_flow(
        cred_client,
        writer_id,
        priv,
        tester_id,
        tester_priv,
        reviewer_id,
        reviewer_priv,
        task_id,
    )

    default_score = cred_client.get(
        f"/agents/{writer_id}/credibility", params={"project_id": "default"}
    ).json()
    source_score = next(
        c["score"]
        for c in default_score["capabilities"]
        if c["capability"] == "codewriter"
    )
    assert source_score > INITIAL_SCORE

    cred_client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "test-owner",
            "capabilities": ["codewriter"],
            "project_ids": ["news-hub"],
        },
    )

    import_response = cred_client.post(
        f"/agents/{writer_id}/credibility/import",
        json={
            "source_project_id": "default",
            "target_project_id": "news-hub",
            "capabilities": ["codewriter"],
        },
    )
    assert import_response.status_code == 200
    imports = import_response.json()["imports"]
    assert len(imports) == 1
    expected = compute_imported_score(source_score)
    assert imports[0]["imported_score"] == pytest.approx(expected)

    hub_score = cred_client.get(
        f"/agents/{writer_id}/credibility", params={"project_id": "news-hub"}
    ).json()
    hub_writer = next(
        c for c in hub_score["capabilities"] if c["capability"] == "codewriter"
    )
    assert hub_writer["score"] == pytest.approx(expected)

    duplicate = cred_client.post(
        f"/agents/{writer_id}/credibility/import",
        json={
            "source_project_id": "default",
            "target_project_id": "news-hub",
            "capabilities": ["codewriter"],
        },
    )
    assert duplicate.status_code == 400
    assert "already imported" in duplicate.json()["detail"]
