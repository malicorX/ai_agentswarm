import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentswarm_platform.auth import create_owner_token
from agentswarm_platform.main import app
from agentswarm_platform.store import Store


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "test-bootstrap")
    monkeypatch.delenv("AGENTSWARM_AUTH_DISABLED", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "auth.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = Store(db_path)
        deps.bind_store(main_module.store)
        yield TestClient(main_module.app)


def test_task_create_requires_auth(auth_client: TestClient) -> None:
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
