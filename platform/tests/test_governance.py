from fastapi.testclient import TestClient


def test_list_governance_templates(client: TestClient) -> None:
    response = client.get("/governance/templates")
    assert response.status_code == 200
    templates = response.json()
    template_ids = {item["template_id"] for item in templates}
    assert "minimal" in template_ids
    assert "news-hub" in template_ids


def test_get_governance_template(client: TestClient) -> None:
    response = client.get("/governance/templates/news-hub")
    assert response.status_code == 200
    body = response.json()
    assert body["template_id"] == "news-hub"
    assert "defaults" in body
    assert body["defaults"]["replication"]["slots"] == 3


def test_create_project_with_governance_template(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json={
            "project_id": "pilot-hub",
            "name": "Pilot Hub",
            "governance_template_id": "news-hub",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "pilot-hub"
    assert body["governance_template_id"] == "news-hub"
    assert body["governance_config"]["moderation"]["min_canary_attempts"] == 2

    governance = client.get("/projects/pilot-hub/governance").json()
    assert governance["governance_template_id"] == "news-hub"

    memory = client.get("/memory/pilot-hub.news-backlog")
    assert memory.status_code == 200
    assert memory.json()["content"]["articles"] == []

    audit = client.get("/audit", params={"limit": 20}).json()
    assert any(event["event_type"] == "project.bootstrapped" for event in audit)
    bootstrapped = next(
        event for event in audit if event["event_type"] == "project.bootstrapped"
    )
    assert bootstrapped["details"]["task_ids"]


def test_unknown_governance_template_rejected(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json={
            "name": "Bad",
            "governance_template_id": "does-not-exist",
        },
    )
    assert response.status_code == 400
    assert "unknown governance template" in response.json()["detail"]
