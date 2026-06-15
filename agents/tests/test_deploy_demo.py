import pytest
from fastapi.testclient import TestClient

from agentswarm_agents.deploy_demo import run_deploy_demo


def test_deploy_demo_invariants(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)
    run_deploy_demo(cred_client)
