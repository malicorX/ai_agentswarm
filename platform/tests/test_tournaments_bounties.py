from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.bounty import parse_bounty_bonus
from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload
from agentswarm_platform.replication import parse_parallel_config
from test_task_flow import register_agent


def test_parse_bounty_bonus_shapes() -> None:
    assert parse_bounty_bonus({}) == 0.0
    assert parse_bounty_bonus({"bounty": 5}) == 5.0
    assert parse_bounty_bonus({"bounty": {"credibility_bonus": 3.5}}) == 3.5


def test_parse_tournament_config() -> None:
    cfg = parse_parallel_config(
        "creative.text",
        {"brief": "haiku", "tournament": {"slots": 2, "quorum": 2}},
    )
    assert cfg is not None
    assert cfg.kind == "tournament"
    assert cfg.slots == 2
    assert cfg.good_attempt_mint == 1.0


def _submit_label(
    client: TestClient,
    claim_token: str,
    task_id: str,
    priv: bytes,
    label: str,
) -> dict:
    result = {"label": label}
    signature = sign_payload(priv, {"task_id": task_id, "result": result})
    response = client.post(
        "/tasks/submit",
        json={"claim_token": claim_token, "result": result, "signature": signature},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_tournament_good_attempt_for_losing_slot(cred_client: TestClient) -> None:
    agents: list[tuple[str, bytes]] = []
    for i in range(3):
        pub, priv = generate_keypair()
        response = cred_client.post(
            "/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"classifier-{i}",
                "capabilities": ["classifier"],
            },
        )
        assert response.status_code == 200
        agents.append((response.json()["agent_id"], priv))

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "classifier.label",
            "capability_required": "classifier",
            "payload": {
                "text": "Election tech policy",
                "labels": ["tech", "politics", "sports"],
                "tournament": {"slots": 3, "quorum": 2, "good_attempt_mint": 1.5},
            },
        },
    )
    assert create.status_code == 200
    group_id = create.json()["payload"]["replication_group_id"]

    labels = ["tech", "politics", "tech"]
    claims: list[tuple[str, str, bytes]] = []
    for agent_id, priv in agents:
        tasks = cred_client.get(
            "/tasks/poll",
            params={"agent_id": agent_id, "capability": "classifier"},
        ).json()
        assert len(tasks) >= 1
        task_id = tasks[0]["task_id"]
        claim = cred_client.post(
            f"/tasks/{task_id}/claim", json={"agent_id": agent_id}
        )
        assert claim.status_code == 200
        claims.append((claim.json()["claim_token"], task_id, priv))

    for (claim_token, task_id, priv), label in zip(claims, labels, strict=True):
        _submit_label(cred_client, claim_token, task_id, priv, label)

    group = cred_client.get(f"/replication/{group_id}").json()
    assert group["status"] == "quorum_met"
    assert group["parallel_kind"] == "tournament"

    scores: dict[str, float] = {}
    for task in group["tasks"]:
        agent_id = task["agent_id"]
        cred = cred_client.get(f"/agents/{agent_id}/credibility").json()
        scores[agent_id] = next(
            row["score"]
            for row in cred["capabilities"]
            if row["capability"] == "classifier"
        )

    winner_scores = [s for aid, s in scores.items() if s > 12.0]
    loser_scores = [s for aid, s in scores.items() if s < 12.0]
    assert len(winner_scores) == 2
    assert len(loser_scores) == 1
    assert loser_scores[0] == pytest.approx(11.5, abs=0.01)


def test_bounty_mint_on_verified_article(cred_client: TestClient) -> None:
    writer_id, writer_priv = register_agent(
        cred_client, ["codewriter"], owner="bounty-writer"
    )
    tester_id, tester_priv = register_agent(cred_client, ["tester"], owner="bounty-tester")
    reviewer_id, reviewer_priv = register_agent(
        cred_client, ["reviewer"], owner="bounty-reviewer"
    )

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.add-article",
            "capability_required": "codewriter",
            "payload": {
                "article": {
                    "id": "bounty-article",
                    "title": "Bounty test",
                    "summary": "Extra credibility on verify.",
                    "url": "https://example.com/bounty",
                    "source": "test",
                    "published_at": "2026-06-15T12:00:00+00:00",
                    "topics": [],
                },
                "bounty": {"credibility_bonus": 4.0},
            },
        },
    )
    assert create.status_code == 200
    task_id = create.json()["task_id"]

    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    article_result = {
        "article_id": "bounty-article",
        "applied": True,
        "article_count": 1,
    }
    signature = sign_payload(
        writer_priv, {"task_id": task_id, "result": article_result}
    )
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": article_result,
            "signature": signature,
        },
    )

    tester_tasks = cred_client.get(
        "/tasks/poll", params={"agent_id": tester_id, "capability": "tester"}
    ).json()
    t_claim = cred_client.post(
        f"/tasks/{tester_tasks[0]['task_id']}/claim", json={"agent_id": tester_id}
    )
    test_result = {"passed": True, "notes": "ok"}
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": t_claim.json()["claim_token"],
            "result": test_result,
            "signature": sign_payload(
                tester_priv,
                {"task_id": tester_tasks[0]["task_id"], "result": test_result},
            ),
        },
    )

    reviewer_tasks = cred_client.get(
        "/tasks/poll", params={"agent_id": reviewer_id, "capability": "reviewer"}
    ).json()
    r_task = reviewer_tasks[0]
    r_claim = cred_client.post(
        f"/tasks/{r_task['task_id']}/claim", json={"agent_id": reviewer_id}
    )
    review_result = {"approved": True, "notes": "ship it"}
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": r_claim.json()["claim_token"],
            "result": review_result,
            "signature": sign_payload(
                reviewer_priv,
                {"task_id": r_task["task_id"], "result": review_result},
            ),
        },
    )

    cred = cred_client.get(f"/agents/{writer_id}/credibility").json()
    writer_score = next(
        row["score"]
        for row in cred["capabilities"]
        if row["capability"] == "codewriter"
    )
    assert writer_score > 14.0
