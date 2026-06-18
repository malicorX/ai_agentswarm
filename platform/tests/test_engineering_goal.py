from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.coordinator_plan import (
    build_default_engineering_goal_plan,
    validate_coordinator_plan,
)
from agentswarm_platform.crypto import sign_payload
from test_coordinator_decompose import RUBRIC, _presence, _submit
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


ENGINEERING_GOAL = {
    "goal_id": "goal-eng-1",
    "poster_agent_id": "agent-poster",
    "brief": "Print first 100 primes",
    "rubric": [{"id": "quality", "weight": 1.0}],
    "min_reviewers": 1,
    "goal_kind": "engineering",
    "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
}


def test_build_default_engineering_goal_plan() -> None:
    plan = build_default_engineering_goal_plan(ENGINEERING_GOAL)
    assert plan["pool_needs"][0]["task_type"] == "codewriter.patch"
    assert plan["deferred_pool_needs"][0]["after_task_type"] == "codewriter.patch"
    assert plan["deferred_pool_needs"][1]["after_task_type"] == "tester.run"
    validate_coordinator_plan(plan, goal_id="goal-eng-1", goal_kind="engineering")


def test_engineering_goal_end_to_end(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-eng")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-eng"
    )
    coder_id, coder_priv = register_agent(dispatch_client, ["codewriter"], owner="coder-eng")
    tester_id, tester_priv = register_agent(dispatch_client, ["tester"], owner="tester-eng")
    reviewer_id, reviewer_priv = register_agent(dispatch_client, ["reviewer"], owner="reviewer-eng")

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
            "brief": ENGINEERING_GOAL["brief"],
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": ENGINEERING_GOAL["verification_spec"],
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200, goal_resp.text
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    assert coord_assignment is not None
    plan = build_default_engineering_goal_plan({**ENGINEERING_GOAL, "goal_id": goal_id})
    _submit(dispatch_client, coordinator_id, coord_priv, coord_assignment, plan)

    coder_assignment = dispatch_client.get(
        f"/agents/{coder_id}/assignments/pending"
    ).json()
    assert coder_assignment is not None
    _submit(
        dispatch_client,
        coder_id,
        coder_priv,
        coder_assignment,
        {"applied": True, "fixture": "primes", "file": "primes.py"},
    )

    tester_assignment = dispatch_client.get(
        f"/agents/{tester_id}/assignments/pending"
    ).json()
    assert tester_assignment is not None
    _submit(
        dispatch_client,
        tester_id,
        tester_priv,
        tester_assignment,
        {"passed": True, "fixture": "primes"},
    )

    reviewer_assignment = dispatch_client.get(
        f"/agents/{reviewer_id}/assignments/pending"
    ).json()
    assert reviewer_assignment is not None
    _submit(
        dispatch_client,
        reviewer_id,
        reviewer_priv,
        reviewer_assignment,
        {"approved": True, "notes": "engineering chain ok"},
    )

    goal = dispatch_client.get(f"/creative/goals/{goal_id}").json()
    assert goal["status"] == "verified"
    assert goal["goal_kind"] == "engineering"

    trace = dispatch_client.get(f"/creative/goals/{goal_id}/trace").json()
    assert trace["goal_id"] == goal_id
    roles = [step["role"] for step in trace["steps"]]
    assert roles == ["coordinator", "codewriter", "tester", "reviewer"]
    assert trace["steps"][0]["owner"] == "coord-eng"
    assert trace["steps"][1]["owner"] == "coder-eng"
    assert all(step["result_summary"] for step in trace["steps"])
    assert trace["steps"][0].get("work_description")
    assert trace.get("code_workspace", {}).get("mode") == "local_fixture"


def test_engineering_reviewer_dispatched_after_tester_submit(
    dispatch_client: TestClient,
) -> None:
    """Isolated goals: reviewer pool need must dispatch without waiting for reviewer heartbeat."""
    run_id = "iso-dispatch"
    owners = [
        f"demo-coordinator-{run_id}",
        f"demo-codewriter-{run_id}",
        f"demo-tester-{run_id}",
        f"demo-reviewer-{run_id}",
    ]
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-iso")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner=owners[0]
    )
    coder_id, coder_priv = register_agent(
        dispatch_client, ["codewriter"], owner=owners[1]
    )
    tester_id, tester_priv = register_agent(dispatch_client, ["tester"], owner=owners[2])
    reviewer_id, reviewer_priv = register_agent(
        dispatch_client, ["reviewer"], owner=owners[3]
    )

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
            "brief": ENGINEERING_GOAL["brief"],
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": ENGINEERING_GOAL["verification_spec"],
            "min_reviewers": 1,
            "dispatch_include_owners": owners,
        },
    )
    assert goal_resp.status_code == 200, goal_resp.text
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    plan = build_default_engineering_goal_plan({**ENGINEERING_GOAL, "goal_id": goal_id})
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
    assert tester_assignment is not None
    _submit(
        dispatch_client,
        tester_id,
        tester_priv,
        tester_assignment,
        {"passed": True, "fixture": "primes"},
    )

    reviewer_assignment = dispatch_client.get(
        f"/agents/{reviewer_id}/assignments/pending"
    ).json()
    assert reviewer_assignment is not None
    assert reviewer_assignment["task_type"] == "reviewer.approve"


def _presence_reviewer(
    dispatch_client: TestClient,
    agent_id: str,
    *,
    vram_gb: float = 12.0,
) -> None:
    response = dispatch_client.post(
        f"/agents/{agent_id}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "vram_gb": vram_gb,
            "ttl_sec": 120,
        },
    )
    assert response.status_code == 200


def _submit_reviewer(
    client: TestClient,
    agent_id: str,
    private_key: bytes,
    assignment: dict,
    result: dict,
) -> dict:
    signature = sign_payload(private_key, {"task_id": assignment["task_id"], "result": result})
    response = client.post(
        "/tasks/submit",
        json={
            "claim_token": assignment["claim_token"],
            "result": result,
            "signature": signature,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_high_risk_engineering_reviewer_replication_quorum(
    dispatch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENTSWARM_HARDWARE_GATES_ENFORCE", "1")
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-hr")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-hr"
    )
    coder_id, coder_priv = register_agent(dispatch_client, ["codewriter"], owner="coder-hr")
    builder_id, builder_priv = register_agent(
        dispatch_client, ["sandbox.build"], owner="builder-hr"
    )
    tester_id, tester_priv = register_agent(dispatch_client, ["sandbox.test"], owner="tester-hr")
    reviewer_a, reviewer_a_priv = register_agent(
        dispatch_client, ["reviewer"], owner="reviewer-a-hr"
    )
    reviewer_b, reviewer_b_priv = register_agent(
        dispatch_client, ["reviewer"], owner="reviewer-b-hr"
    )

    for agent_id, caps in (
        (coordinator_id, ["coordinator"]),
        (coder_id, ["codewriter"]),
        (builder_id, ["sandbox.build"]),
        (tester_id, ["sandbox.test"]),
    ):
        _presence(dispatch_client, agent_id, caps)
    _presence_reviewer(dispatch_client, reviewer_a)
    _presence_reviewer(dispatch_client, reviewer_b)

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "High-risk primes sandbox",
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": {
                "fixture": "primes",
                "lab": "engineering-lab",
                "workspace_mode": "sandbox",
                "risk_level": "high",
            },
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200, goal_resp.text
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    sandbox_goal = {
        **ENGINEERING_GOAL,
        "goal_id": goal_id,
        "verification_spec": {
            "fixture": "primes",
            "lab": "engineering-lab",
            "workspace_mode": "sandbox",
            "risk_level": "high",
        },
    }
    plan = build_default_engineering_goal_plan(sandbox_goal)
    _submit(dispatch_client, coordinator_id, coord_priv, coord_assignment, plan)

    coder_assignment = dispatch_client.get(f"/agents/{coder_id}/assignments/pending").json()
    _submit(
        dispatch_client,
        coder_id,
        coder_priv,
        coder_assignment,
        {"applied": True, "fixture": "primes", "file": "primes.py"},
    )

    builder_assignment = dispatch_client.get(f"/agents/{builder_id}/assignments/pending").json()
    assert builder_assignment is not None
    _submit(
        dispatch_client,
        builder_id,
        builder_priv,
        builder_assignment,
        {"passed": True, "fixture": "primes", "sandbox": True},
    )

    tester_assignment = dispatch_client.get(f"/agents/{tester_id}/assignments/pending").json()
    assert tester_assignment is not None
    _submit(
        dispatch_client,
        tester_id,
        tester_priv,
        tester_assignment,
        {"passed": True, "fixture": "primes"},
    )

    reviewer_a_assignment = dispatch_client.get(
        f"/agents/{reviewer_a}/assignments/pending"
    ).json()
    reviewer_b_assignment = dispatch_client.get(
        f"/agents/{reviewer_b}/assignments/pending"
    ).json()
    assert reviewer_a_assignment is not None
    assert reviewer_b_assignment is not None
    assert reviewer_a_assignment["task_id"] != reviewer_b_assignment["task_id"]
    task_a = dispatch_client.get(f"/tasks/{reviewer_a_assignment['task_id']}").json()
    task_b = dispatch_client.get(f"/tasks/{reviewer_b_assignment['task_id']}").json()
    group_a = task_a["payload"].get("replication_group_id")
    group_b = task_b["payload"].get("replication_group_id")
    assert group_a and group_a == group_b

    first = _submit_reviewer(
        dispatch_client,
        reviewer_a,
        reviewer_a_priv,
        reviewer_a_assignment,
        {"approved": True, "notes": "first reviewer"},
    )
    assert first.get("replication_status") == "pending"
    goal = dispatch_client.get(f"/creative/goals/{goal_id}").json()
    assert goal["status"] not in ("verified", "rejected")

    second = _submit_reviewer(
        dispatch_client,
        reviewer_b,
        reviewer_b_priv,
        reviewer_b_assignment,
        {"approved": True, "notes": "second reviewer"},
    )
    assert second.get("replication_status") == "quorum_met"

    goal = dispatch_client.get(f"/creative/goals/{goal_id}").json()
    assert goal["status"] == "verified"

    group = dispatch_client.get(f"/replication/{group_a}").json()
    assert group["status"] == "quorum_met"
    assert group["winning_result"]["approved"] is True


def test_high_risk_replication_mints_all_engineering_reviewers(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    monkeypatch.setenv("AGENTSWARM_HARDWARE_GATES_ENFORCE", "1")

    poster_id, _ = register_agent(cred_client, ["codewriter"], owner="poster-hr-cred")
    coordinator_id, coord_priv = register_agent(
        cred_client, ["coordinator"], owner="coord-hr-cred"
    )
    coder_id, coder_priv = register_agent(cred_client, ["codewriter"], owner="coder-hr-cred")
    builder_id, builder_priv = register_agent(
        cred_client, ["sandbox.build"], owner="builder-hr-cred"
    )
    tester_id, tester_priv = register_agent(cred_client, ["sandbox.test"], owner="tester-hr-cred")
    reviewer_a, reviewer_a_priv = register_agent(
        cred_client, ["reviewer"], owner="reviewer-a-hr-cred"
    )
    reviewer_b, reviewer_b_priv = register_agent(
        cred_client, ["reviewer"], owner="reviewer-b-hr-cred"
    )

    for agent_id, caps in (
        (coordinator_id, ["coordinator"]),
        (coder_id, ["codewriter"]),
        (builder_id, ["sandbox.build"]),
        (tester_id, ["sandbox.test"]),
    ):
        _presence(cred_client, agent_id, caps)
    _presence_reviewer(cred_client, reviewer_a)
    _presence_reviewer(cred_client, reviewer_b)

    goal_resp = cred_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": "High-risk primes sandbox credibility",
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": {
                "fixture": "primes",
                "lab": "engineering-lab",
                "workspace_mode": "sandbox",
                "risk_level": "high",
            },
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200, goal_resp.text
    goal_id = goal_resp.json()["goal_id"]

    coord_assignment = cred_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    sandbox_goal = {
        **ENGINEERING_GOAL,
        "goal_id": goal_id,
        "verification_spec": {
            "fixture": "primes",
            "lab": "engineering-lab",
            "workspace_mode": "sandbox",
            "risk_level": "high",
        },
    }
    plan = build_default_engineering_goal_plan(sandbox_goal)
    _submit(cred_client, coordinator_id, coord_priv, coord_assignment, plan)
    coder_assignment = cred_client.get(f"/agents/{coder_id}/assignments/pending").json()
    _submit(
        cred_client,
        coder_id,
        coder_priv,
        coder_assignment,
        {"applied": True, "fixture": "primes", "file": "primes.py"},
    )
    builder_assignment = cred_client.get(f"/agents/{builder_id}/assignments/pending").json()
    _submit(
        cred_client,
        builder_id,
        builder_priv,
        builder_assignment,
        {"passed": True, "fixture": "primes", "sandbox": True},
    )
    tester_assignment = cred_client.get(f"/agents/{tester_id}/assignments/pending").json()
    _submit(
        cred_client,
        tester_id,
        tester_priv,
        tester_assignment,
        {"passed": True, "fixture": "primes"},
    )
    reviewer_a_assignment = cred_client.get(
        f"/agents/{reviewer_a}/assignments/pending"
    ).json()
    reviewer_b_assignment = cred_client.get(
        f"/agents/{reviewer_b}/assignments/pending"
    ).json()
    _submit_reviewer(
        cred_client,
        reviewer_a,
        reviewer_a_priv,
        reviewer_a_assignment,
        {"approved": True},
    )
    _submit_reviewer(
        cred_client,
        reviewer_b,
        reviewer_b_priv,
        reviewer_b_assignment,
        {"approved": True},
    )

    for reviewer_id in (reviewer_a, reviewer_b):
        cred = cred_client.get(f"/agents/{reviewer_id}/credibility").json()
        reviewer_score = next(
            row["score"]
            for row in cred["capabilities"]
            if row.get("capability") == "reviewer"
        )
        assert reviewer_score >= 50.0
