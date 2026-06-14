from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload
from test_task_flow import register_agent


def test_memory_upsert_and_list(client: TestClient) -> None:
    response = client.put(
        "/memory/news-backlog",
        json={
            "key": "news-backlog",
            "content": {
                "articles": [
                    {
                        "id": "art-1",
                        "title": "Test",
                        "summary": "Summary",
                        "url": "https://example.com/1",
                        "source": "example",
                        "published_at": "2026-06-13T00:00:00+00:00",
                        "topics": ["tech"],
                    }
                ]
            },
            "tags": ["pilot"],
        },
    )
    assert response.status_code == 200
    listed = client.get("/memory").json()
    assert "news-backlog" in listed["entries"][0]["key"] or any(
        e["key"] == "news-backlog" for e in listed["entries"]
    )


def test_platform_summary(client: TestClient) -> None:
    summary = client.get("/platform/summary").json()
    assert "tasks" in summary
    assert "memory_keys" in summary


def test_planner_submit_enqueues_codewriter_tasks(client: TestClient) -> None:
    planner_id, planner_priv = register_agent(client, ["planner"])
    create = client.post(
        "/tasks",
        json={
            "task_type": "planner.plan",
            "capability_required": "planner",
            "payload": {"goal": "test-plan"},
        },
    )
    task_id = create.json()["task_id"]
    claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": planner_id})
    result = {
        "goal": "test-plan",
        "enqueue": [
            {
                "task_type": "codewriter.add-article",
                "capability_required": "codewriter",
                "payload": {
                    "article": {
                        "id": "art-plan-1",
                        "title": "Planned",
                        "summary": "From planner",
                        "url": "https://example.com/plan",
                        "source": "planner",
                        "published_at": "2026-06-13T00:00:00+00:00",
                        "topics": [],
                    }
                },
            }
        ],
    }
    signature = sign_payload(planner_priv, {"task_id": task_id, "result": result})
    submit = client.post(
        "/tasks/submit",
        json={"claim_token": claim.json()["claim_token"], "result": result, "signature": signature},
    )
    assert submit.status_code == 200
    assert len(submit.json()["enqueued_task_ids"]) == 1
    writer_id, _writer_priv = register_agent(client, ["codewriter"])
    poll = client.get("/tasks/poll", params={"agent_id": writer_id})
    assert poll.status_code == 200
    assert len(poll.json()) >= 1


def test_orchestrator_scan_enqueues_planner(client: TestClient) -> None:
    client.put(
        "/memory/news-backlog",
        json={
            "key": "news-backlog",
            "content": {"articles": [{"id": "x", "title": "t", "summary": "s", "url": "https://x", "source": "s", "published_at": "2026-06-13T00:00:00+00:00", "topics": []}]},
            "tags": [],
        },
    )
    orch_id, orch_priv = register_agent(client, ["orchestrator"])
    create = client.post(
        "/tasks",
        json={
            "task_type": "orchestrator.scan",
            "capability_required": "orchestrator",
            "payload": {},
        },
    )
    task_id = create.json()["task_id"]
    claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": orch_id})
    result = {
        "gaps": [{"type": "idle_pool_with_backlog"}],
        "enqueue": [
            {
                "task_type": "planner.plan",
                "capability_required": "planner",
                "payload": {"goal": "drain-news-backlog", "memory_key": "news-backlog"},
            }
        ],
    }
    signature = sign_payload(orch_priv, {"task_id": task_id, "result": result})
    submit = client.post(
        "/tasks/submit",
        json={"claim_token": claim.json()["claim_token"], "result": result, "signature": signature},
    )
    assert submit.status_code == 200
    assert submit.json()["enqueued_task_ids"]
