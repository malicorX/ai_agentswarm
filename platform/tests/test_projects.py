from agentswarm_platform.crypto import generate_keypair, public_key_b64


def test_default_project_seeded(client):
    response = client.get("/projects")
    assert response.status_code == 200
    projects = response.json()
    assert any(p["project_id"] == "default" for p in projects)


def test_create_project_and_scoped_tasks(client):
    create = client.post(
        "/projects",
        json={"project_id": "news-hub", "name": "AI News Hub"},
    )
    assert create.status_code == 200
    assert create.json()["project_id"] == "news-hub"

    pub, _ = generate_keypair()
    reg = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "alice",
            "capabilities": ["codewriter"],
            "project_ids": ["news-hub"],
        },
    )
    agent_id = reg.json()["agent_id"]

    other_pub, _ = generate_keypair()
    other = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(other_pub),
            "owner": "bob",
            "capabilities": ["codewriter"],
        },
    )
    other_id = other.json()["agent_id"]

    scoped = client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "index.html"},
            "project_id": "news-hub",
        },
    )
    assert scoped.status_code == 200
    assert scoped.json()["project_id"] == "news-hub"

    default_task = client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": "other.html"},
        },
    )
    assert default_task.status_code == 200

    hub_poll = client.get(
        f"/tasks/poll?agent_id={agent_id}&capability=codewriter"
    ).json()
    hub_ids = {task["task_id"] for task in hub_poll}
    assert scoped.json()["task_id"] in hub_ids
    assert default_task.json()["task_id"] not in hub_ids

    default_poll = client.get(
        f"/tasks/poll?agent_id={other_id}&capability=codewriter"
    ).json()
    default_ids = {task["task_id"] for task in default_poll}
    assert default_task.json()["task_id"] in default_ids
    assert scoped.json()["task_id"] not in default_ids


def test_unknown_project_rejected(client):
    response = client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {},
            "project_id": "missing-project",
        },
    )
    assert response.status_code == 400
    assert "unknown project" in response.json()["detail"]
