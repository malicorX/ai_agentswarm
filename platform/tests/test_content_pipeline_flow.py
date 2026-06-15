from fastapi.testclient import TestClient

from agentswarm_platform.crypto import sign_payload
from test_task_flow import register_agent

DRAFT = {
    "url": "https://example.com/news",
    "title": "Agent framework update",
    "raw_text": "A long article about agents and orchestration in production.",
    "source": "example.com",
    "published_at": "2026-06-15T10:00:00+00:00",
}


def _submit(client: TestClient, agent_id: str, priv: bytes, task_id: str, result: dict) -> dict:
    claim = client.post(f"/tasks/{task_id}/claim", json={"agent_id": agent_id})
    assert claim.status_code == 200
    signature = sign_payload(priv, {"task_id": task_id, "result": result})
    submit = client.post(
        "/tasks/submit",
        json={
            "claim_token": claim.json()["claim_token"],
            "result": result,
            "signature": signature,
        },
    )
    assert submit.status_code == 200
    return submit.json()


def test_scraper_summarizer_classifier_chain_enqueues_codewriter(client: TestClient) -> None:
    scraper_id, scraper_priv = register_agent(
        client, ["scraper"], egress_allowlist=["example.com"]
    )
    create = client.post(
        "/tasks",
        json={
            "task_type": "scraper.fetch",
            "capability_required": "scraper",
            "payload": {"url": "https://example.com/news", "pipeline": True},
        },
    )
    scraper_task = create.json()["task_id"]
    scraper_submit = _submit(
        client,
        scraper_id,
        scraper_priv,
        scraper_task,
        {**DRAFT, "mode": "page"},
    )
    summarizer_task = scraper_submit["enqueued_task_ids"][0]

    summarizer_id, summarizer_priv = register_agent(client, ["summarizer"])
    summarizer_submit = _submit(
        client,
        summarizer_id,
        summarizer_priv,
        summarizer_task,
        {"draft": DRAFT, "summary": "Agents in production."},
    )
    classifier_task = summarizer_submit["enqueued_task_ids"][0]

    classifier_id, classifier_priv = register_agent(client, ["classifier"])
    classifier_submit = _submit(
        client,
        classifier_id,
        classifier_priv,
        classifier_task,
        {"label": "agents"},
    )
    writer_tasks = classifier_submit["enqueued_task_ids"]
    assert writer_tasks

    writer_id, _writer_priv = register_agent(client, ["codewriter"])
    poll = client.get("/tasks/poll", params={"agent_id": writer_id, "capability": "codewriter"})
    assert poll.status_code == 200
    polled_ids = {item["task_id"] for item in poll.json()}
    assert writer_tasks[0] in polled_ids
    assert scraper_id  # used
