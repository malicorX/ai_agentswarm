import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agentswarm_platform.credibility as credibility
from agentswarm_platform.credibility import (
    engineering_verify_reviewer_mint,
    min_credibility_for_tier,
)
from test_task_flow import register_agent


def test_min_credibility_for_tier_defaults() -> None:
    assert min_credibility_for_tier(1) == 0.0
    assert min_credibility_for_tier(2) == 25.0
    assert min_credibility_for_tier(3) == 50.0


def test_engineering_verify_reviewer_mint_reaches_high_tier_floor() -> None:
    assert engineering_verify_reviewer_mint(10.0) == 50.0
    assert engineering_verify_reviewer_mint(60.0) == 0.0


def test_high_tier_claim_rejected_for_new_agent(cred_client: TestClient) -> None:
    writer_id, _ = register_agent(cred_client, ["codewriter"])

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "stake_tier": "high"},
        },
    )
    assert create.status_code == 200
    task_id = create.json()["task_id"]

    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    assert claim.status_code == 400
    assert "credibility floor not met" in claim.json()["detail"]
    assert "stake_tier=high" in claim.json()["detail"]


def test_high_tier_hidden_from_poll_for_new_agent(cred_client: TestClient) -> None:
    writer_id, _ = register_agent(cred_client, ["codewriter"])

    cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "stake_tier": "high"},
        },
    )

    poll = cred_client.get(
        "/tasks/poll", params={"agent_id": writer_id, "capability": "codewriter"}
    )
    assert poll.status_code == 200
    assert poll.json() == []


def test_high_tier_claimable_with_sufficient_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_AUTH_DISABLED", "1")
    monkeypatch.setenv("AGENTSWARM_CREDIBILITY_ENABLED", "1")
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        client = TestClient(main_module.app)

        writer_id, _ = register_agent(client, ["codewriter"])
        cred = client.get(f"/agents/{writer_id}/credibility").json()
        writer_score = next(
            c["score"] for c in cred["capabilities"] if c["capability"] == "codewriter"
        )
        assert writer_score >= min_credibility_for_tier(3)

        create = client.post(
            "/tasks",
            json={
                "task_type": "codewriter.patch",
                "capability_required": "codewriter",
                "payload": {"file": "index.html", "stake_tier": "high"},
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
        assert claim.status_code == 200


def test_medium_tier_rejected_at_initial_score(cred_client: TestClient) -> None:
    writer_id, _ = register_agent(cred_client, ["codewriter"])
    cred = cred_client.get(f"/agents/{writer_id}/credibility").json()
    writer_score = next(
        c["score"] for c in cred["capabilities"] if c["capability"] == "codewriter"
    )
    assert writer_score == credibility.INITIAL_SCORE

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "stake_tier": "medium"},
        },
    )
    task_id = create.json()["task_id"]
    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    assert claim.status_code == 400
    assert "stake_tier=medium" in claim.json()["detail"]
