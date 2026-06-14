from fastapi.testclient import TestClient


def test_platform_api_projects_and_templates(client: TestClient) -> None:
    templates = client.get("/governance/templates").json()
    assert any(t["template_id"] == "minimal" for t in templates)

    created = client.post(
        "/projects",
        json={
            "project_id": "sdk-test",
            "name": "SDK Test",
            "governance_template_id": "minimal",
        },
    )
    assert created.status_code == 200
    assert created.json()["project_id"] == "sdk-test"

    projects = client.get("/projects").json()
    assert any(p["project_id"] == "sdk-test" for p in projects)

    governance = client.get("/projects/sdk-test/governance").json()
    assert governance["project_id"] == "sdk-test"
