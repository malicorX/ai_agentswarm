from fastapi.testclient import TestClient

from agentswarm_platform.crypto import generate_keypair, public_key_b64


def register_agent(
    client: TestClient,
    capabilities: list[str],
    *,
    budget: dict[str, int] | None = None,
    egress: list[str] | None = None,
) -> str:
    pub, _priv = generate_keypair()
    body: dict = {
        "public_key": public_key_b64(pub),
        "owner": "test-owner",
        "capabilities": capabilities,
    }
    if budget is not None:
        body["resource_budget"] = budget
    if egress is not None:
        body["egress_allowlist"] = egress
    response = client.post("/agents/register", json=body)
    assert response.status_code == 200
    return response.json()["agent_id"]


def create_task(client: TestClient, capability: str = "codewriter") -> str:
    response = client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": capability,
            "payload": {},
        },
    )
    assert response.status_code == 200
    return response.json()["task_id"]


def test_concurrent_claim_limit_enforced(client: TestClient) -> None:
    agent_id = register_agent(
        client, ["codewriter"], budget={"max_concurrent_claims": 1, "max_claims_per_hour": 10}
    )
    task_a = create_task(client)
    task_b = create_task(client)

    first = client.post(f"/tasks/{task_a}/claim", json={"agent_id": agent_id})
    assert first.status_code == 200

    second = client.post(f"/tasks/{task_b}/claim", json={"agent_id": agent_id})
    assert second.status_code == 429
    assert "concurrent" in second.json()["detail"].lower()


def test_budget_status_endpoint(client: TestClient) -> None:
    agent_id = register_agent(client, ["codewriter"])
    create_task(client)

    status = client.get(f"/agents/{agent_id}/budget")
    assert status.status_code == 200
    data = status.json()
    assert data["agent_id"] == agent_id
    assert data["usage"]["concurrent_claims"] == 0
    assert data["resource_budget"]["max_concurrent_claims"] >= 1
    assert isinstance(data["egress_allowlist"], list)


def test_invalid_egress_host_rejected(client: TestClient) -> None:
    pub, _priv = generate_keypair()
    response = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "test-owner",
            "capabilities": ["scraper"],
            "egress_allowlist": ["https://evil.com/path"],
        },
    )
    assert response.status_code == 400
    assert "egress" in response.json()["detail"].lower()


def test_scraper_requires_explicit_egress_by_default(client: TestClient) -> None:
    pub, _priv = generate_keypair()
    response = client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "test-owner",
            "capabilities": ["scraper"],
        },
    )
    assert response.status_code == 400
    assert "egress" in response.json()["detail"].lower()
