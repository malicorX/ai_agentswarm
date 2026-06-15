from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.assignment_config import assignment_mode
from agentswarm_platform.assignment_signing import sign_assignment, verify_assignment
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


def test_assignment_mode_defaults_to_pull(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_ASSIGNMENT_MODE", raising=False)
    assert assignment_mode() == "pull"


def test_assignment_signature_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    payload = {"lease_id": "lease-1", "agent_id": "agent-1", "task_id": "task-1", "expires_at": "2026-06-15T00:00:00+00:00"}
    signature = sign_assignment(payload)
    assert verify_assignment(payload, signature)


def test_presence_heartbeat(dispatch_client: TestClient) -> None:
    agent_id, _ = register_agent(dispatch_client, ["reviewer"], owner="presence-owner")
    response = dispatch_client.post(
        f"/agents/{agent_id}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-test",
            "load": 0.1,
            "ttl_sec": 120,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == agent_id
    assert body["status"] == "idle"


def test_assignment_only_task_not_in_poll(dispatch_client: TestClient) -> None:
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    create = dispatch_client.post(
        "/tasks",
        json={
            "task_type": "reviewer.subjective",
            "capability_required": "reviewer",
            "payload": {"capsule": {"brief": "review poem"}},
            "assignment_only": True,
        },
    )
    assert create.status_code == 200
    polled = dispatch_client.get("/tasks/poll", params={"agent_id": reviewer_id, "capability": "reviewer"})
    assert polled.json() == []


def test_assignment_only_rejects_manual_claim(dispatch_client: TestClient) -> None:
    register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    create = dispatch_client.post(
        "/tasks",
        json={
            "task_type": "reviewer.subjective",
            "capability_required": "reviewer",
            "payload": {"capsule": {"brief": "review poem"}},
            "assignment_only": True,
        },
    )
    task_id = create.json()["task_id"]
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-c")
    claim = dispatch_client.post(f"/tasks/{task_id}/claim", json={"agent_id": reviewer_id})
    assert claim.status_code == 400
    assert "assignment-only" in claim.json()["detail"]


def test_pool_need_assigns_disjoint_reviewer(dispatch_client: TestClient) -> None:
    poster_id, _ = register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-owner")
    dispatch_client.post(
        f"/agents/{reviewer_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    dispatch_client.post(
        f"/agents/{poster_id}/presence",
        json={"status": "idle", "capabilities": ["codewriter"], "ttl_sec": 120},
    )
    need = dispatch_client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {
                "capsule": {
                    "brief": "Score this poem",
                    "rubric": [{"id": "quality", "weight": 1.0}],
                }
            },
            "constraints": {"exclude_owners": ["poster-owner"]},
        },
    )
    assert need.status_code == 200
    body = need.json()
    assert body["assigned"] is True
    assignment = body["assignment"]
    assert assignment is not None
    assert assignment["task_id"] == body["task_id"]
    pending = dispatch_client.get(f"/agents/{reviewer_id}/assignments/pending")
    assert pending.status_code == 200
    pending_body = pending.json()
    assert pending_body is not None
    assert pending_body["task_id"] == body["task_id"]
    assert pending_body["claim_token"]
    poster_pending = dispatch_client.get(f"/agents/{poster_id}/assignments/pending")
    assert poster_pending.json() is None


def test_pool_need_rejects_pull_mode(client: TestClient) -> None:
    response = client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {},
        },
    )
    assert response.status_code == 400
    assert "dispatch" in response.json()["detail"]


def _post_reviewer_need(
    dispatch_client: TestClient,
    *,
    exclude_owners: list[str] | None = None,
) -> dict:
    response = dispatch_client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {
                "capsule": {
                    "brief": "Score this poem",
                    "rubric": [{"id": "quality", "weight": 1.0}],
                }
            },
            "constraints": {"exclude_owners": exclude_owners or ["poster-owner"]},
        },
    )
    assert response.status_code == 200
    return response.json()


def test_pool_need_redispatches_on_idle_presence(dispatch_client: TestClient) -> None:
    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    need = _post_reviewer_need(dispatch_client)
    assert need["assigned"] is False

    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-owner")
    dispatch_client.post(
        f"/agents/{reviewer_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )

    pending = dispatch_client.get(f"/agents/{reviewer_id}/assignments/pending")
    assert pending.status_code == 200
    pending_body = pending.json()
    assert pending_body is not None
    assert pending_body["task_id"] == need["task_id"]


def test_pool_need_redispatches_second_pending_need(dispatch_client: TestClient) -> None:
    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    need_one = _post_reviewer_need(dispatch_client)
    need_two = _post_reviewer_need(dispatch_client)
    assert need_one["assigned"] is False
    assert need_two["assigned"] is False

    reviewer_one_id, _ = register_agent(
        dispatch_client, ["reviewer"], owner="reviewer-owner-a"
    )
    dispatch_client.post(
        f"/agents/{reviewer_one_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    first_pending = dispatch_client.get(
        f"/agents/{reviewer_one_id}/assignments/pending"
    ).json()
    assert first_pending is not None

    reviewer_two_id, _ = register_agent(
        dispatch_client, ["reviewer"], owner="reviewer-owner-b"
    )
    dispatch_client.post(
        f"/agents/{reviewer_two_id}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    second_pending = dispatch_client.get(
        f"/agents/{reviewer_two_id}/assignments/pending"
    ).json()
    assert second_pending is not None
    assigned_task_ids = {first_pending["task_id"], second_pending["task_id"]}
    assert assigned_task_ids == {need_one["task_id"], need_two["task_id"]}


def test_expired_lease_reclaimed_on_idle_presence(
    dispatch_client: TestClient,
) -> None:
    from agentswarm_platform import main as platform_main

    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    reviewer_a, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    dispatch_client.post(
        f"/agents/{reviewer_a}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    need = _post_reviewer_need(dispatch_client)
    assert need["assigned"] is True
    assigned = dispatch_client.get(f"/agents/{reviewer_a}/assignments/pending").json()
    assert assigned is not None

    with platform_main.store._conn() as conn:
        conn.execute(
            "UPDATE assignment_leases SET expires_at = ? WHERE status = 'active'",
            ("2020-01-01T00:00:00+00:00",),
        )

    reviewer_b, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    dispatch_client.post(
        f"/agents/{reviewer_b}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    reclaimed = dispatch_client.get(f"/agents/{reviewer_b}/assignments/pending").json()
    assert reclaimed is not None
    assert reclaimed["task_id"] == need["task_id"]
    assert dispatch_client.get(f"/agents/{reviewer_a}/assignments/pending").json() is None


def test_stale_presence_lease_reclaimed_on_idle_presence(
    dispatch_client: TestClient,
) -> None:
    from agentswarm_platform import main as platform_main

    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    reviewer_a, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    dispatch_client.post(
        f"/agents/{reviewer_a}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    need = _post_reviewer_need(dispatch_client)
    assert need["assigned"] is True

    with platform_main.store._conn() as conn:
        conn.execute(
            "UPDATE agent_presence SET last_seen_at = ? WHERE agent_id = ?",
            ("2020-01-01T00:00:00+00:00", reviewer_a),
        )

    reviewer_b, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    dispatch_client.post(
        f"/agents/{reviewer_b}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    reclaimed = dispatch_client.get(f"/agents/{reviewer_b}/assignments/pending").json()
    assert reclaimed is not None
    assert reclaimed["task_id"] == need["task_id"]


def test_stale_presence_reclaim_respects_include_owners(
    dispatch_client: TestClient,
) -> None:
    from agentswarm_platform import main as platform_main

    run_id = "stale-include"
    owner_a = f"lease-reclaim-{run_id}-a"
    owner_b = f"lease-reclaim-{run_id}-b"
    reviewer_a, _ = register_agent(dispatch_client, ["reviewer"], owner=owner_a)
    reviewer_b, _ = register_agent(dispatch_client, ["reviewer"], owner=owner_b)
    dispatch_client.post(
        f"/agents/{reviewer_a}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "vram_gb": 8.0,
            "ttl_sec": 5,
        },
    )
    need = dispatch_client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {
                "capsule": {
                    "brief": "Score this poem",
                    "rubric": [{"id": "quality", "weight": 1.0}],
                }
            },
            "constraints": {"include_owners": [owner_a, owner_b]},
        },
    )
    assert need.status_code == 200
    body = need.json()
    assert body["assigned"] is True
    task_id = body["task_id"]

    with platform_main.store._conn() as conn:
        conn.execute(
            "UPDATE agent_presence SET last_seen_at = ? WHERE agent_id = ?",
            ("2020-01-01T00:00:00+00:00", reviewer_a),
        )

    dispatch_client.post(
        f"/agents/{reviewer_b}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "vram_gb": 8.0,
            "ttl_sec": 120,
        },
    )
    reclaimed = dispatch_client.get(
        f"/agents/{reviewer_b}/assignments/pending"
    ).json()
    assert reclaimed is not None
    assert reclaimed["task_id"] == task_id


def test_orphaned_claimed_task_reconciled_on_idle_presence(
    dispatch_client: TestClient,
) -> None:
    from agentswarm_platform import main as platform_main

    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    reviewer_a, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    dispatch_client.post(
        f"/agents/{reviewer_a}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    need = _post_reviewer_need(dispatch_client)
    assert need["assigned"] is True

    with platform_main.store._conn() as conn:
        conn.execute(
            "UPDATE assignment_leases SET status = 'expired' WHERE status = 'active'"
        )
        conn.execute(
            """
            UPDATE pool_needs
            SET status = 'pending', assigned_agent_id = NULL, lease_id = NULL
            WHERE task_id = ?
            """,
            (need["task_id"],),
        )

    reviewer_b, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    dispatch_client.post(
        f"/agents/{reviewer_b}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    reclaimed = dispatch_client.get(f"/agents/{reviewer_b}/assignments/pending").json()
    assert reclaimed is not None
    assert reclaimed["task_id"] == need["task_id"]


def test_orphaned_assigned_need_reconciled_on_idle_presence(
    dispatch_client: TestClient,
) -> None:
    from agentswarm_platform import main as platform_main

    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    reviewer_a, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    dispatch_client.post(
        f"/agents/{reviewer_a}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    need = _post_reviewer_need(dispatch_client)
    assert need["assigned"] is True

    with platform_main.store._conn() as conn:
        conn.execute(
            "UPDATE assignment_leases SET status = 'expired' WHERE status = 'active'"
        )
        conn.execute(
            "UPDATE tasks SET status = 'created', claimed_by = NULL, claim_token = NULL, claim_deadline = NULL"
        )

    reviewer_b, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    dispatch_client.post(
        f"/agents/{reviewer_b}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    reclaimed = dispatch_client.get(f"/agents/{reviewer_b}/assignments/pending").json()
    assert reclaimed is not None
    assert reclaimed["task_id"] == need["task_id"]


def test_idle_presence_skips_generic_coordinator_backlog(
    dispatch_client: TestClient,
) -> None:
    """Volunteers warming up before an isolated goal must not take stale pool work."""
    from agentswarm_platform import main as platform_main

    with platform_main.store._conn() as conn:
        for index in range(5):
            conn.execute(
                """
                INSERT INTO pool_needs (
                    need_id, role, capability_required, parent_task_id, task_id,
                    project_id, constraints_json, status, created_at
                ) VALUES (?, 'coordinator', 'coordinator', ?, ?, 'default', '{}', 'pending', ?)
                """,
                (
                    f"need-generic-backlog-{index}",
                    f"task-generic-backlog-{index}",
                    f"task-generic-backlog-{index}",
                    f"2020-01-01T00:{index:02d}:00+00:00",
                ),
            )

    coordinator_id, _ = register_agent(
        dispatch_client, ["coordinator"], owner="demo-coordinator-isolated"
    )
    dispatch_client.post(
        f"/agents/{coordinator_id}/presence",
        json={"status": "idle", "capabilities": ["coordinator"], "ttl_sec": 120},
    )
    pending = dispatch_client.get(
        f"/agents/{coordinator_id}/assignments/pending"
    ).json()
    assert pending is None


def test_prepare_pool_need_redispatches_orphaned_claimed_task(
    dispatch_client: TestClient,
) -> None:
    """Worst-case orphan: expired lease, task still claimed, need still assigned."""
    from agentswarm_platform import main as platform_main

    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    reviewer_a, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    dispatch_client.post(
        f"/agents/{reviewer_a}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    need = _post_reviewer_need(dispatch_client)
    assert need["assigned"] is True

    with platform_main.store._conn() as conn:
        conn.execute(
            "UPDATE assignment_leases SET status = 'expired' WHERE status = 'active'"
        )

    reviewer_b, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    dispatch_client.post(
        f"/agents/{reviewer_b}/presence",
        json={"status": "idle", "capabilities": ["reviewer"], "ttl_sec": 120},
    )
    reclaimed = dispatch_client.get(f"/agents/{reviewer_b}/assignments/pending").json()
    assert reclaimed is not None
    assert reclaimed["task_id"] == need["task_id"]


def test_redispatch_skips_backlogged_needs_for_unrelated_capability(
    dispatch_client: TestClient,
) -> None:
    """Idle reviewer redispatch must not be blocked by older coordinator backlog."""
    from agentswarm_platform import main as platform_main

    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    with platform_main.store._conn() as conn:
        for index in range(40):
            conn.execute(
                """
                INSERT INTO pool_needs (
                    need_id, role, capability_required, parent_task_id, task_id,
                    project_id, constraints_json, status, created_at
                ) VALUES (?, 'coordinator', 'coordinator', ?, ?, 'default', '{}', 'pending', ?)
                """,
                (
                    f"need-backlog-{index}",
                    f"task-backlog-{index}",
                    f"task-backlog-{index}",
                    f"2020-01-01T00:{index:02d}:00+00:00",
                ),
            )

    reviewer_a, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-a")
    reviewer_b, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-b")
    dispatch_client.post(
        f"/agents/{reviewer_a}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "vram_gb": 8.0,
            "ttl_sec": 5,
        },
    )
    need = dispatch_client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {
                "capsule": {
                    "brief": "Score this poem",
                    "rubric": [{"id": "quality", "weight": 1.0}],
                }
            },
            "constraints": {"include_owners": ["reviewer-a", "reviewer-b"]},
        },
    )
    assert need.status_code == 200
    body = need.json()
    assert body["assigned"] is True
    task_id = body["task_id"]

    with platform_main.store._conn() as conn:
        conn.execute(
            "UPDATE agent_presence SET last_seen_at = ? WHERE agent_id = ?",
            ("2020-01-01T00:00:00+00:00", reviewer_a),
        )

    dispatch_client.post(
        f"/agents/{reviewer_b}/presence",
        json={
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "vram_gb": 8.0,
            "ttl_sec": 120,
        },
    )
    reclaimed = dispatch_client.get(f"/agents/{reviewer_b}/assignments/pending").json()
    assert reclaimed is not None
    assert reclaimed["task_id"] == task_id


def test_pool_need_include_owners_restricts_dispatch(
    dispatch_client: TestClient,
) -> None:
    register_agent(dispatch_client, ["codewriter"], owner="poster-owner")
    swarm_id, _ = register_agent(dispatch_client, ["reviewer"], owner="swarm-reviewer")
    isolated_id, _ = register_agent(dispatch_client, ["reviewer"], owner="isolated-reviewer")
    for agent_id in (swarm_id, isolated_id):
        dispatch_client.post(
            f"/agents/{agent_id}/presence",
            json={
                "status": "idle",
                "capabilities": ["reviewer"],
                "model_id": "llm-mock-v1",
                "vram_gb": 8.0,
                "ttl_sec": 120,
            },
        )
    from agentswarm_platform import main as platform_main
    from agentswarm_platform.dispatcher import select_agent_for_need

    with platform_main.store._conn() as conn:
        selected = select_agent_for_need(
            conn,
            capability_required="reviewer",
            constraints={"include_owners": ["isolated-reviewer"]},
        )
    assert selected is not None
    assert selected["owner"] == "isolated-reviewer"

    need = dispatch_client.post(
        "/pool/need",
        json={
            "role": "reviewer",
            "capability_required": "reviewer",
            "task_type": "reviewer.subjective",
            "payload": {
                "capsule": {
                    "brief": "Score this poem",
                    "rubric": [{"id": "quality", "weight": 1.0}],
                }
            },
            "constraints": {
                "exclude_owners": ["poster-owner"],
                "include_owners": ["isolated-reviewer"],
            },
        },
    )
    assert need.status_code == 200
    body = need.json()
    assert body["assigned"] is True
    assert (
        dispatch_client.get(f"/agents/{isolated_id}/assignments/pending").json()
        is not None
    )
    assert dispatch_client.get(f"/agents/{swarm_id}/assignments/pending").json() is None
