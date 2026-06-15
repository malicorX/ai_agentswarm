from test_task_flow import register_agent


def test_agent_profile_includes_levels_and_badges(cred_client) -> None:
    import agentswarm_platform.credibility as credibility
    from agentswarm_platform.crypto import sign_payload as sp

    writer_id, writer_priv = register_agent(cred_client, ["codewriter"])
    tester_id, tester_priv = register_agent(cred_client, ["tester"])
    reviewer_id, reviewer_priv = register_agent(cred_client, ["reviewer"])

    create = cred_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html", "stake_tier": "low"},
        },
    )
    task_id = create.json()["task_id"]
    claim = cred_client.post(f"/tasks/{task_id}/claim", json={"agent_id": writer_id})
    claim_token = claim.json()["claim_token"]
    result = {"file": "index.html", "applied": True}
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": claim_token,
            "result": result,
            "signature": sp(writer_priv, {"task_id": task_id, "result": result}),
        },
    )

    tester_tasks = cred_client.get(
        "/tasks/poll", params={"agent_id": tester_id, "capability": "tester"}
    ).json()
    tester_task_id = tester_tasks[0]["task_id"]
    tester_claim = cred_client.post(
        f"/tasks/{tester_task_id}/claim", json={"agent_id": tester_id}
    )
    tester_token = tester_claim.json()["claim_token"]
    test_result = {"passed": True, "tests_run": 1}
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": tester_token,
            "result": test_result,
            "signature": sp(
                tester_priv, {"task_id": tester_task_id, "result": test_result}
            ),
        },
    )

    reviewer_tasks = cred_client.get(
        "/tasks/poll", params={"agent_id": reviewer_id, "capability": "reviewer"}
    ).json()
    reviewer_task_id = reviewer_tasks[0]["task_id"]
    reviewer_claim = cred_client.post(
        f"/tasks/{reviewer_task_id}/claim", json={"agent_id": reviewer_id}
    )
    reviewer_token = reviewer_claim.json()["claim_token"]
    review_result = {"approved": True, "notes": "ok"}
    cred_client.post(
        "/tasks/submit",
        json={
            "claim_token": reviewer_token,
            "result": review_result,
            "signature": sp(
                reviewer_priv,
                {"task_id": reviewer_task_id, "result": review_result},
            ),
        },
    )

    profile = cred_client.get(f"/agents/{writer_id}/profile").json()
    assert profile["agent_id"] == writer_id
    assert profile["project_id"] == "default"
    assert profile["declared_capabilities"] == ["codewriter"]
    writer_cred = next(
        row for row in profile["credibility"] if row["capability"] == "codewriter"
    )
    assert writer_cred["score"] > credibility.INITIAL_SCORE
    assert writer_cred["level"]["label"] in ("novice", "apprentice", "journeyman")
    badge_ids = {badge["id"] for badge in profile["badges"]}
    assert "first_accept" in badge_ids
    assert profile["aggregate_level"]["label"] == writer_cred["level"]["label"]


def test_agent_profile_not_found(cred_client) -> None:
    response = cred_client.get("/agents/agent_missing/profile")
    assert response.status_code == 404
