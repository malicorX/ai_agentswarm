import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.crypto import sign_payload
from agentswarm_platform.memory_policy import project_id_for_memory_key
from test_task_flow import register_agent


def test_project_id_for_memory_key() -> None:
    assert project_id_for_memory_key("news-backlog") == "default"
    assert project_id_for_memory_key("hub.news-backlog") == "hub"
    assert project_id_for_memory_key("plain-key") == "default"


def _signed_memory_body(
    agent_id: str,
    priv: bytes,
    *,
    memory_key: str = "news-backlog",
    content: dict | None = None,
    tags: list[str] | None = None,
) -> dict:
    content = content or {"articles": []}
    tags = tags or []
    signature = sign_payload(
        priv,
        {
            "memory_key": memory_key,
            "content": content,
            "tags": tags,
            "agent_id": agent_id,
        },
    )
    return {
        "key": memory_key,
        "content": content,
        "tags": tags,
        "agent_id": agent_id,
        "signature": signature,
    }


def test_agent_memory_write_rejected_below_credibility_floor(
    cred_client: TestClient,
) -> None:
    orch_id, orch_priv = register_agent(cred_client, ["orchestrator"])

    response = cred_client.put(
        "/memory/news-backlog",
        json=_signed_memory_body(orch_id, orch_priv),
    )
    assert response.status_code == 400
    assert "credibility floor not met" in response.json()["detail"]


def test_agent_memory_write_rejects_missing_capability(cred_client: TestClient) -> None:
    writer_id, writer_priv = register_agent(cred_client, ["codewriter"])

    response = cred_client.put(
        "/memory/news-backlog",
        json=_signed_memory_body(writer_id, writer_priv),
    )
    assert response.status_code == 400
    assert "memory-write capability" in response.json()["detail"]


def test_agent_memory_write_succeeds_with_sufficient_credibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_AUTH_DISABLED", "1")
    monkeypatch.setenv("AGENTSWARM_CREDIBILITY_ENABLED", "1")
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 30.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 30.0)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        client = TestClient(main_module.app)

        orch_id, orch_priv = register_agent(client, ["orchestrator"])
        body = _signed_memory_body(
            orch_id,
            orch_priv,
            content={"articles": [{"id": "a1"}]},
            tags=["agent-write"],
        )
        response = client.put("/memory/news-backlog", json=body)
        assert response.status_code == 200
        assert response.json()["content"]["articles"][0]["id"] == "a1"

        audit = client.get("/audit", params={"limit": 5}).json()
        assert any(event["event_type"] == "memory.updated" for event in audit)


def test_agent_memory_write_scoped_to_project_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_AUTH_DISABLED", "1")
    monkeypatch.setenv("AGENTSWARM_CREDIBILITY_ENABLED", "1")
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 30.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 30.0)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        client = TestClient(main_module.app)

        client.post(
            "/projects",
            json={"project_id": "hub", "name": "Hub"},
        )
        orch_id, orch_priv = register_agent(
            client, ["orchestrator"], project_ids=["default"]
        )

        response = client.put(
            "/memory/hub.news-backlog",
            json=_signed_memory_body(
                orch_id,
                orch_priv,
                memory_key="hub.news-backlog",
            ),
        )
        assert response.status_code == 400
        assert "not a member of project hub" in response.json()["detail"]
