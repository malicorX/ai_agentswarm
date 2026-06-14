from fastapi.testclient import TestClient


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
