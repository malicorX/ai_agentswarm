import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_AUTH_DISABLED", "1")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        yield TestClient(main_module.app)


@pytest.fixture
def cred_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_AUTH_DISABLED", "1")
    monkeypatch.setenv("AGENTSWARM_CREDIBILITY_ENABLED", "1")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        yield TestClient(main_module.app)


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("AGENTSWARM_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AGENTSWARM_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "test-bootstrap")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        yield TestClient(main_module.app)
