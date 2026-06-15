from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload
from test_task_flow import register_agent


def _register_versioned(
    client: TestClient,
    capabilities: list[str],
    version_signature: str,
) -> tuple[str, bytes]:
    pub_raw, priv_raw = generate_keypair()
    response = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub_raw),
            "owner": "probation-test",
            "capabilities": capabilities,
            "version_signature": version_signature,
        },
    )
    assert response.status_code == 200
    return response.json()["agent_id"], priv_raw


def _seed_codewriter_score(cred_client: TestClient, agent_id: str, delta: float) -> None:
    import agentswarm_platform.main as main_module

    with main_module.store._conn() as conn:
        from agentswarm_platform.credibility_ledger import _apply_delta

        _apply_delta(
            conn,
            agent_id=agent_id,
            capability="codewriter",
            project_id="default",
            delta=delta,
            reason="test.seed",
            ref_type="test",
            ref_id="test",
            details={},
            apply_decay_before=False,
        )


def test_major_bump_starts_probation(cred_client: TestClient) -> None:
    pub, _priv = generate_keypair()
    body = {
        "public_key": public_key_b64(pub),
        "owner": "probation-start",
        "capabilities": ["codewriter"],
        "version_signature": "codewriter-v1.0",
    }
    reg = cred_client.post("/agents/register", json=body)
    agent_id = reg.json()["agent_id"]

    agent = cred_client.get(f"/agents/{agent_id}").json()
    assert agent["version_probation_remaining"] == 0

    body["version_signature"] = "codewriter-v2.0"
    cred_client.post("/agents/register", json=body)

    agent = cred_client.get(f"/agents/{agent_id}").json()
    assert agent["version_probation_remaining"] == 3

    profile = cred_client.get(f"/agents/{agent_id}/profile").json()
    assert profile["version_probation"]["active"] is True
    assert profile["version_probation"]["remaining"] == 3


def test_probation_blocks_medium_tier_despite_score(cred_client: TestClient) -> None:
    writer_id, _ = _register_versioned(cred_client, ["codewriter"], "codewriter-v1.0")
    _seed_codewriter_score(cred_client, writer_id, 50.0)

    import agentswarm_platform.main as main_module

    with main_module.store._conn() as conn:
        row = conn.execute(
            "SELECT public_key FROM agents WHERE agent_id = ?", (writer_id,)
        ).fetchone()
        pub_b64 = row["public_key"]

    cred_client.post(
        "/agents/register",
        json={
            "public_key": pub_b64,
            "owner": "probation-test",
            "capabilities": ["codewriter"],
            "version_signature": "codewriter-v2.0",
        },
    )

    cred = cred_client.get(f"/agents/{writer_id}/credibility").json()
    score = next(c["score"] for c in cred["capabilities"] if c["capability"] == "codewriter")
    assert score >= 25.0

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "stake_tier": "medium"},
        },
    )
    assert create.status_code == 200
    task_id = create.json()["task_id"]

    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    assert claim.status_code == 400
    assert "probation" in claim.json()["detail"]
    assert "stake_tier=medium" in claim.json()["detail"]


def test_probation_clears_after_verified_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_AUTH_DISABLED", "1")
    monkeypatch.setenv("AGENTSWARM_CREDIBILITY_ENABLED", "1")
    monkeypatch.setenv("AGENTSWARM_VERSION_PROBATION_VERIFICATIONS", "1")
    monkeypatch.delenv("AGENTSWARM_CRED_INITIAL", raising=False)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        client = TestClient(main_module.app)

        writer_id, writer_priv = _register_versioned(
            client, ["codewriter"], "codewriter-v1.0"
        )
        _seed_codewriter_score(client, writer_id, 50.0)
        tester_id, tester_priv = register_agent(client, ["tester"])
        reviewer_id, reviewer_priv = register_agent(client, ["reviewer"])

        import agentswarm_platform.main as mm

        with mm.store._conn() as conn:
            row = conn.execute(
                "SELECT public_key FROM agents WHERE agent_id = ?", (writer_id,)
            ).fetchone()
            pub_b64 = row["public_key"]

        client.post(
            "/agents/register",
            json={
                "public_key": pub_b64,
                "owner": "probation-test",
                "capabilities": ["codewriter"],
                "version_signature": "codewriter-v2.0",
            },
        )
        assert client.get(f"/agents/{writer_id}").json()["version_probation_remaining"] == 1

        create = client.post(
            "/tasks",
            json={
                "task_type": "codewriter.patch",
                "capability_required": "codewriter",
                "payload": {"file": "index.html", "stake_tier": "low"},
            },
        )
        task_id = create.json()["task_id"]
        claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
        claim_token = claim.json()["claim_token"]
        result = {"file": "index.html", "applied": True}
        signature = sign_payload(writer_priv, {"task_id": task_id, "result": result})
        client.post(
            "/tasks/submit",
            json={"claim_token": claim_token, "result": result, "signature": signature},
        )

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
        review_result = {"approved": True, "notes": "ok"}
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

        assert client.get(f"/tasks/{task_id}").json()["status"] == "verified"
        assert (
            client.get(f"/agents/{writer_id}").json()["version_probation_remaining"] == 0
        )

        create_medium = client.post(
            "/tasks",
            json={
                "task_type": "codewriter.patch",
                "capability_required": "codewriter",
                "payload": {"file": "other.html", "stake_tier": "medium"},
            },
        )
        medium_id = create_medium.json()["task_id"]
        medium_claim = client.post(
            f"/tasks/{medium_id}/claim", json={"agent_id": writer_id}
        )
        assert medium_claim.status_code == 200
