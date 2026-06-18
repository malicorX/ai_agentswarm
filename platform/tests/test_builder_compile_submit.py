from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.coordinator_plan import build_default_engineering_goal_plan
from agentswarm_platform.crypto import sign_payload
from test_coordinator_decompose import _presence, _submit
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


SANDBOX_GOAL = {
    "goal_id": "goal-sandbox-builder",
    "brief": "Primes in sandbox",
    "rubric": [{"id": "quality", "weight": 1.0}],
    "min_reviewers": 1,
    "goal_kind": "engineering",
    "verification_spec": {
        "fixture": "primes",
        "lab": "engineering-lab",
        "workspace_mode": "sandbox",
    },
}


def test_builder_compile_submit_enqueues_tester(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-sb")
    coordinator_id, coord_priv = register_agent(
        dispatch_client, ["coordinator"], owner="coord-sb"
    )
    coder_id, coder_priv = register_agent(dispatch_client, ["codewriter"], owner="coder-sb")
    builder_id, builder_priv = register_agent(
        dispatch_client, ["sandbox.build"], owner="builder-sb"
    )
    tester_id, _ = register_agent(dispatch_client, ["sandbox.test"], owner="tester-sb")
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-sb")

    for agent_id, caps in (
        (coordinator_id, ["coordinator"]),
        (coder_id, ["codewriter"]),
        (builder_id, ["sandbox.build"]),
        (tester_id, ["sandbox.test"]),
        (reviewer_id, ["reviewer"]),
    ):
        _presence(dispatch_client, agent_id, caps)

    goal_resp = dispatch_client.post(
        "/creative/goals",
        json={
            "poster_agent_id": poster_id,
            "brief": SANDBOX_GOAL["brief"],
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": SANDBOX_GOAL["verification_spec"],
            "min_reviewers": 1,
        },
    )
    assert goal_resp.status_code == 200, goal_resp.text
    goal_id = goal_resp.json()["goal_id"]

    plan = build_default_engineering_goal_plan({**SANDBOX_GOAL, "goal_id": goal_id})
    coord_assignment = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    _submit(dispatch_client, coordinator_id, coord_priv, coord_assignment, plan)

    coder_assignment = dispatch_client.get(f"/agents/{coder_id}/assignments/pending").json()
    _submit(
        dispatch_client,
        coder_id,
        coder_priv,
        coder_assignment,
        {
            "applied": True,
            "patch": {"file": "primes.py"},
            "workspace_ref": "local-patch",
        },
    )

    builder_assignment = dispatch_client.get(
        f"/agents/{builder_id}/assignments/pending"
    ).json()
    assert builder_assignment is not None
    assert builder_assignment["task_type"] == "builder.compile"

    build_result = {
        "passed": True,
        "sandbox": True,
        "stdout": "compile ok\n",
        "stderr": "",
        "build_artifact": {
            "passed": True,
            "command": "python -m compileall -q .",
            "stdout_digest": "abc",
        },
    }
    _submit(dispatch_client, builder_id, builder_priv, builder_assignment, build_result)

    tester_assignment = dispatch_client.get(f"/agents/{tester_id}/assignments/pending").json()
    assert tester_assignment is not None
    assert tester_assignment["task_type"] == "tester.run"

    trace = dispatch_client.get(f"/creative/goals/{goal_id}/trace").json()
    builder_step = next(s for s in trace["steps"] if s["role"] == "builder")
    assert builder_step["phase"] == "build"
    assert builder_step.get("sandbox_host_owner") == "builder-sb"
    assert builder_step.get("log_artifact_ref", "").startswith("sha256:")

    stored = dispatch_client.get(f"/artifacts/{builder_step['log_artifact_ref']}").json()
    decoded = base64.b64decode(stored["content_base64"]).decode("utf-8")
    assert "compile ok" in decoded
