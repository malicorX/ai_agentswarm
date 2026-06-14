from fastapi.testclient import TestClient

from agentswarm_platform.auth import create_owner_token


def test_task_create_without_auth_returns_401(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {},
        },
    )
    assert response.status_code == 401


def test_bootstrap_token_allows_task_create(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {},
        },
        headers={"X-Bootstrap-Token": "test-bootstrap"},
    )
    assert response.status_code == 200


def test_owner_jwt_allows_register(auth_client: TestClient) -> None:
    import agentswarm_platform.main as main_module

    owner = main_module.store.upsert_owner(
        github_user_id="12345", github_login="alice"
    )
    token = create_owner_token(
        owner_id=owner["owner_id"],
        github_user_id="12345",
        github_login="alice",
    )
    from agentswarm_platform.crypto import generate_keypair, public_key_b64

    pub, _priv = generate_keypair()
    response = auth_client.post(
        "/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": "alice",
            "capabilities": ["codewriter"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    agent = auth_client.get(f"/agents/{response.json()['agent_id']}").json()
    assert agent["owner_id"] == owner["owner_id"]
