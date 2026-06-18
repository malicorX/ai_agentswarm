from fastapi.testclient import TestClient


from agentswarm_platform.capabilities import agent_satisfies_capability


def test_agent_satisfies_capability_sandbox_aliases() -> None:
    assert agent_satisfies_capability(["sandbox.linux"], "sandbox.build")
    assert agent_satisfies_capability(["sandbox.linux"], "sandbox.test")
    assert agent_satisfies_capability(["sandbox.windows"], "sandbox.windows.build")
    assert agent_satisfies_capability(["sandbox.windows"], "sandbox.windows.test")
    assert not agent_satisfies_capability(["sandbox.build"], "sandbox.test")
    assert agent_satisfies_capability(["sandbox.build"], "sandbox.build")


def test_unknown_capability_rejected(client: TestClient) -> None:
    response = client.post(
        "/agents/register",
        json={
            "public_key": "cHVi",
            "owner": "test",
            "capabilities": ["not-a-real-capability"],
        },
    )
    assert response.status_code == 400
    assert "unknown capabilities" in response.json()["detail"]


def test_list_capabilities(client: TestClient) -> None:
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data
    ids = {c["id"] for c in data["capabilities"]}
    assert "codewriter" in ids
    assert "sandbox.linux" in ids
    assert "sandbox.build" in ids
    assert "sandbox.test" in ids
    assert "sandbox.windows.build" in ids
