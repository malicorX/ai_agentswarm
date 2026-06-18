from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.coordinator_plan import build_default_engineering_goal_plan
from agentswarm_platform.crypto import sign_payload
from agentswarm_platform.goal_artifacts import (
    refs_from_submission_result,
    select_primary_deploy_artifact_ref,
)
from test_coordinator_decompose import _presence, _submit
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_refs_from_submission_result_collects_log_bundle() -> None:
    refs = refs_from_submission_result(
        {
            "passed": True,
            "run_artifact": {"log_artifact_ref": "sha256:" + "a" * 64},
            "build_artifact": {"log_artifact_ref": "sha256:" + "b" * 64},
        }
    )
    assert refs == [f"sha256:{'a' * 64}", f"sha256:{'b' * 64}"]


def test_select_primary_prefers_last_sha256() -> None:
    refs = [f"sha256:{'b' * 64}", f"sha256:{'c' * 64}"]
    primary = select_primary_deploy_artifact_ref(refs, {"verification_spec": {}})
    assert primary == f"sha256:{'c' * 64}"


def test_verified_goal_deploy_request_uses_primary_artifact(
    dispatch_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_DEPLOY_REQUIRE_ARTIFACT_BLOB", "0")
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-deploy")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-deploy"
    )
    coder_id, coder_priv = register_agent(dispatch_client, ["codewriter"], owner="coder-deploy")
    tester_id, tester_priv = register_agent(dispatch_client, ["tester"], owner="tester-deploy")
    reviewer_id, reviewer_priv = register_agent(dispatch_client, ["reviewer"], owner="reviewer-deploy")

    for agent_id, caps in (
        (coordinator_id, ["coordinator"]),
        (coder_id, ["codewriter"]),
        (tester_id, ["tester"]),
        (reviewer_id, ["reviewer"]),
    ):
        _presence(dispatch_client, agent_id, caps)

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "Deploy bridge goal",
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
            "min_reviewers": 1,
        },
    )
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": goal_id,
            "brief": "Deploy bridge goal",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
        }
    )
    _submit(dispatch_client, coordinator_id, coord_priv, coord_assignment, plan)

    coder_assignment = dispatch_client.get(f"/agents/{coder_id}/assignments/pending").json()
    _submit(
        dispatch_client,
        coder_id,
        coder_priv,
        coder_assignment,
        {"applied": True, "fixture": "primes", "file": "primes.py"},
    )

    tester_assignment = dispatch_client.get(f"/agents/{tester_id}/assignments/pending").json()
    _submit(
        dispatch_client,
        tester_id,
        tester_priv,
        tester_assignment,
        {
            "passed": True,
            "fixture": "primes",
            "sandbox": True,
            "stdout": "ok",
            "stderr": "",
        },
    )

    reviewer_assignment = dispatch_client.get(
        f"/agents/{reviewer_id}/assignments/pending"
    ).json()
    _submit(
        dispatch_client,
        reviewer_id,
        reviewer_priv,
        reviewer_assignment,
        {"approved": True},
    )

    goal = dispatch_client.get(f"/creative/goals/{goal_id}").json()
    assert goal["status"] == "verified"
    primary = goal["primary_artifact_ref"]
    assert primary and str(primary).startswith("sha256:")
    assert primary in goal["artifact_refs"]

    trace = dispatch_client.get(f"/creative/goals/{goal_id}/trace").json()
    assert trace["primary_artifact_ref"] == primary

    deploy = dispatch_client.post(
        f"/creative/goals/{goal_id}/deploy-request",
        json={
            "environment": "staging",
            "description": "from verified goal",
            "required_signoffs": 1,
        },
    )
    assert deploy.status_code == 200, deploy.text
    body = deploy.json()
    assert body["artifact_ref"] == primary
    assert body["goal_id"] == goal_id
    assert len(body["approve_task_ids"]) == 1


def test_engineering_reviewer_can_sign_deploy_after_verify(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    monkeypatch.setenv("AGENTSWARM_DEPLOY_REQUIRE_ARTIFACT_BLOB", "0")

    poster_id, _ = register_agent(cred_client, ["codewriter"], owner="poster-cred-deploy")
    coordinator_id, coord_priv = register_agent(
        cred_client, ["coordinator"], owner="coord-cred-deploy"
    )
    coder_id, coder_priv = register_agent(cred_client, ["codewriter"], owner="coder-cred-deploy")
    tester_id, tester_priv = register_agent(cred_client, ["tester"], owner="tester-cred-deploy")
    reviewer_id, reviewer_priv = register_agent(
        cred_client, ["reviewer"], owner="reviewer-cred-deploy"
    )

    for agent_id, caps in (
        (coordinator_id, ["coordinator"]),
        (coder_id, ["codewriter"]),
        (tester_id, ["tester"]),
        (reviewer_id, ["reviewer"]),
    ):
        _presence(cred_client, agent_id, caps)

    goal_resp = cred_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "cred deploy signoff",
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200, goal_resp.text
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = cred_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    plan = build_default_engineering_goal_plan(
        {
            "goal_id": goal_id,
            "poster_agent_id": poster_id,
            "brief": "cred deploy signoff",
            "rubric": [],
            "min_reviewers": 1,
            "goal_kind": "engineering",
            "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
        }
    )
    _submit(cred_client, coordinator_id, coord_priv, coord_assignment, plan)
    coder_assignment = cred_client.get(f"/agents/{coder_id}/assignments/pending").json()
    _submit(
        cred_client,
        coder_id,
        coder_priv,
        coder_assignment,
        {"applied": True, "fixture": "primes", "file": "primes.py"},
    )
    tester_assignment = cred_client.get(f"/agents/{tester_id}/assignments/pending").json()
    _submit(
        cred_client,
        tester_id,
        tester_priv,
        tester_assignment,
        {"passed": True, "fixture": "primes", "sandbox": True, "stdout": "ok", "stderr": ""},
    )
    reviewer_assignment = cred_client.get(
        f"/agents/{reviewer_id}/assignments/pending"
    ).json()
    _submit(
        cred_client,
        reviewer_id,
        reviewer_priv,
        reviewer_assignment,
        {"approved": True},
    )

    cred = cred_client.get(f"/agents/{reviewer_id}/credibility").json()
    reviewer_score = next(
        row["score"]
        for row in cred["capabilities"]
        if row.get("capability") == "reviewer"
    )
    assert reviewer_score >= 50.0

    deploy = cred_client.post(
        f"/creative/goals/{goal_id}/deploy-request",
        json={"environment": "staging", "required_signoffs": 1},
    )
    assert deploy.status_code == 200, deploy.text
    approve_task_id = deploy.json()["approve_task_ids"][0]

    claim = cred_client.post(
        f"/tasks/{approve_task_id}/claim",
        json={"agent_id": reviewer_id},
    )
    assert claim.status_code == 200, claim.text
    result = {"decision": "approve"}
    submit = cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": result,
            "signature": sign_payload(
                reviewer_priv, {"task_id": approve_task_id, "result": result}
            ),
        },
    )
    assert submit.status_code == 200, submit.text


def test_deploy_request_rejects_unverified_goal(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-pending")
    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "pending",
            "rubric": [{"id": "quality", "weight": 1.0}],
            "goal_kind": "engineering",
            "verification_spec": {"fixture": "primes"},
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200, goal_resp.text
    goal_id = goal_resp.json()["goal_id"]
    response = dispatch_client.post(
        f"/creative/goals/{goal_id}/deploy-request",
        json={"environment": "staging", "artifact_ref": "sha-demo"},
    )
    assert response.status_code == 400
    assert "verified" in response.json()["detail"]
