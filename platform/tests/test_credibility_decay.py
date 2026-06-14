from agentswarm_platform import main as main_module
from test_task_flow import register_agent


def test_inactivity_decay_on_credibility_read(cred_client) -> None:
    writer_id, _ = register_agent(cred_client, ["codewriter"])
    with main_module.store._conn() as conn:
        conn.execute(
            """
            UPDATE credibility_balances
            SET updated_at = ?, score = ?
            WHERE agent_id = ? AND capability = ?
            """,
            ("2024-01-01T00:00:00+00:00", 100.0, writer_id, "codewriter"),
        )

    cred = cred_client.get(f"/agents/{writer_id}/credibility").json()
    writer_score = next(
        row["score"] for row in cred["capabilities"] if row["capability"] == "codewriter"
    )
    assert writer_score < 100.0
    assert writer_score >= 0.0


def test_apply_decay_batch_endpoint(cred_client) -> None:
    writer_id, _ = register_agent(cred_client, ["codewriter"])
    with main_module.store._conn() as conn:
        conn.execute(
            """
            UPDATE credibility_balances
            SET updated_at = ?, score = ?
            WHERE agent_id = ? AND capability = ?
            """,
            ("2024-06-01T00:00:00+00:00", 80.0, writer_id, "codewriter"),
        )

    response = cred_client.post("/credibility/apply-decay")
    assert response.status_code == 200
    body = response.json()
    assert body["checked"] >= 1
    assert body["updated"] >= 1

    cred = cred_client.get(f"/agents/{writer_id}/credibility").json()
    writer_score = next(
        row["score"] for row in cred["capabilities"] if row["capability"] == "codewriter"
    )
    assert writer_score < 80.0


def test_no_decay_within_min_inactivity_window(cred_client) -> None:
    writer_id, _ = register_agent(cred_client, ["codewriter"])
    before = cred_client.get(f"/agents/{writer_id}/credibility").json()
    score = next(
        row["score"] for row in before["capabilities"] if row["capability"] == "codewriter"
    )
    after = cred_client.get(f"/agents/{writer_id}/credibility").json()
    score_again = next(
        row["score"] for row in after["capabilities"] if row["capability"] == "codewriter"
    )
    assert score_again == score
