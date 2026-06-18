import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolate_credibility_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_CRED_INITIAL", raising=False)
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 10.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 10.0)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_AUTH_DISABLED", "1")
    monkeypatch.delenv("AGENTSWARM_CRED_INITIAL", raising=False)
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
    monkeypatch.delenv("AGENTSWARM_CRED_INITIAL", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("AGENTSWARM_DB", str(db_path))
        import agentswarm_platform.deps as deps
        import agentswarm_platform.main as main_module

        main_module.store = main_module.Store(db_path)
        deps.bind_store(main_module.store)
        yield TestClient(main_module.app)


@pytest.fixture
def live_dispatch_platform(tmp_path: Path):
    """Start uvicorn with dispatch mode for volunteer-client integration tests."""
    import dispatch_e2e_support

    base_url, proc = dispatch_e2e_support.start_live_dispatch_platform(tmp_path)
    try:
        yield base_url
    finally:
        dispatch_e2e_support.stop_process(proc)


@pytest.fixture
def e2e_dispatch_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import dispatch_e2e_support

    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", dispatch_e2e_support.E2E_ASSIGNMENT_SECRET)
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "e2e-bootstrap")
    monkeypatch.setenv("AGENTSWARM_IDENTITY_DIR", str(tmp_path / "worker-identities"))
    monkeypatch.setenv("AGENTSWARM_REPO_ROOT", str(Path(__file__).resolve().parents[2]))
