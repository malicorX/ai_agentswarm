import agentswarm_platform.credibility as credibility
from agentswarm_platform.credibility_ledger import seed_agent_capabilities
from agentswarm_platform.owner_anchoring import (
    CANARY_PENALTY,
    FLAG_HIGH_PENALTY,
    QUARANTINE_PENALTY,
    add_owner_penalty,
    anchored_initial_score,
    ensure_owner_anchoring_schema,
)
import agentswarm_platform.main as main_module
from test_task_flow import register_agent


def test_anchored_initial_score_caps_at_zero() -> None:
    initial = credibility.INITIAL_SCORE
    assert anchored_initial_score(0) == initial
    assert anchored_initial_score(QUARANTINE_PENALTY) == initial - QUARANTINE_PENALTY
    assert anchored_initial_score(initial + 10) == 0.0


def test_seed_uses_owner_penalty_for_new_capability(cred_client) -> None:
    writer_id, _ = register_agent(cred_client, ["codewriter"])
    owner_id = "owner_anchor_test"
    with main_module.store._conn() as conn:
        ensure_owner_anchoring_schema(conn)
        conn.execute(
            """
            INSERT INTO owners (owner_id, github_user_id, github_login, created_at, penalty_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (owner_id, "gid-anchor", "anchor-user", "2026-06-13T00:00:00+00:00", 0.0),
        )
        conn.execute(
            "UPDATE agents SET owner_id = ? WHERE agent_id = ?",
            (owner_id, writer_id),
        )
        add_owner_penalty(conn, owner_id, QUARANTINE_PENALTY)
        seed_agent_capabilities(conn, writer_id, ["reviewer"])

    cred = cred_client.get(f"/agents/{writer_id}/credibility").json()
    reviewer_score = next(
        row["score"] for row in cred["capabilities"] if row["capability"] == "reviewer"
    )
    assert reviewer_score == anchored_initial_score(QUARANTINE_PENALTY)


def test_quarantine_applies_owner_penalty(cred_client) -> None:
    from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload

    owner_id = "owner_quarantine_test"
    with main_module.store._conn() as conn:
        ensure_owner_anchoring_schema(conn)
        conn.execute(
            """
            INSERT INTO owners (owner_id, github_user_id, github_login, created_at, penalty_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (owner_id, "gid-q", "quarantine-user", "2026-06-13T00:00:00+00:00", 0.0),
        )

    pub, priv = generate_keypair()
    register = cred_client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "quarantine-user",
            "capabilities": ["codewriter"],
        },
    )
    agent_id = register.json()["agent_id"]
    with main_module.store._conn() as conn:
        conn.execute(
            "UPDATE agents SET owner_id = ? WHERE agent_id = ?",
            (owner_id, agent_id),
        )

    mod_id, mod_priv = register_agent(cred_client, ["moderator"])
    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "moderator.scan",
            "capability_required": "moderator",
            "payload": {},
        },
    )
    task_id = create.json()["task_id"]
    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": mod_id})
    result = {
        "actions": [
            {
                "type": "quarantine",
                "agent_id": agent_id,
                "reason": "test anchor",
            }
        ]
    }
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": result,
            "signature": sign_payload(mod_priv, {"task_id": task_id, "result": result}),
        },
    )

    summary = cred_client.get(f"/owners/{owner_id}/anchoring").json()
    assert summary["penalty_score"] == QUARANTINE_PENALTY


def test_owner_anchoring_summary_not_found(cred_client) -> None:
    response = cred_client.get("/owners/owner_missing/anchoring")
    assert response.status_code == 404


def _insert_owner(conn, owner_id: str, login: str) -> None:
    ensure_owner_anchoring_schema(conn)
    conn.execute(
        """
        INSERT INTO owners (owner_id, github_user_id, github_login, created_at, penalty_score)
        VALUES (?, ?, ?, ?, ?)
        """,
        (owner_id, f"gid-{owner_id}", login, "2026-06-13T00:00:00+00:00", 0.0),
    )


def test_canary_failure_applies_owner_penalty(cred_client) -> None:
    from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload

    owner_id = "owner_canary_test"
    with main_module.store._conn() as conn:
        _insert_owner(conn, owner_id, "canary-owner")

    pub, priv = generate_keypair()
    register = cred_client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "canary-owner",
            "capabilities": ["classifier"],
        },
    )
    agent_id = register.json()["agent_id"]
    with main_module.store._conn() as conn:
        conn.execute(
            "UPDATE agents SET owner_id = ? WHERE agent_id = ?",
            (owner_id, agent_id),
        )

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "classifier.label",
            "capability_required": "classifier",
            "payload": {
                "text": "probe",
                "labels": ["tech", "politics"],
                "replication": False,
                "canary": {"expected": {"label": "tech"}},
            },
        },
    )
    task_id = create.json()["task_id"]
    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": agent_id})
    result = {"label": "politics"}
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": result,
            "signature": sign_payload(priv, {"task_id": task_id, "result": result}),
        },
    )

    summary = cred_client.get(f"/owners/{owner_id}/anchoring").json()
    assert summary["penalty_score"] == CANARY_PENALTY


def test_high_flag_applies_owner_penalty(cred_client) -> None:
    from agentswarm_platform.crypto import sign_payload

    owner_id = "owner_flag_test"
    with main_module.store._conn() as conn:
        _insert_owner(conn, owner_id, "flag-owner")

    target_id, _ = register_agent(cred_client, ["codewriter"])
    with main_module.store._conn() as conn:
        conn.execute(
            "UPDATE agents SET owner_id = ? WHERE agent_id = ?",
            (owner_id, target_id),
        )

    mod_id, mod_priv = register_agent(cred_client, ["moderator"])
    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "moderator.scan",
            "capability_required": "moderator",
            "payload": {},
        },
    )
    task_id = create.json()["task_id"]
    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": mod_id})
    result = {
        "actions": [
            {
                "type": "flag",
                "subject_type": "agent",
                "subject_id": target_id,
                "severity": "high",
                "reason": "suspicious pattern",
            }
        ]
    }
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": result,
            "signature": sign_payload(mod_priv, {"task_id": task_id, "result": result}),
        },
    )

    summary = cred_client.get(f"/owners/{owner_id}/anchoring").json()
    assert summary["penalty_score"] == FLAG_HIGH_PENALTY
