import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from agentswarm_agents.deploy_demo import run_deploy_demo

def test_deploy_demo_invariants(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)
    run_deploy_demo(cred_client)


def test_deploy_demo_stages_pilot_when_staging_enabled(
    cred_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    monkeypatch.setattr("agentswarm_platform.credibility.INITIAL_SCORE", 60.0)
    monkeypatch.setattr("agentswarm_platform.credibility_ledger.INITIAL_SCORE", 60.0)
    monkeypatch.setenv("AGENTSWARM_REPO_ROOT", str(repo))
    monkeypatch.setenv("AGENTSWARM_DEPLOY_STAGING", "1")
    monkeypatch.setenv("AGENTSWARM_PILOT_STAGING_DIR", str(tmp_path / "staged"))

    run_deploy_demo(cred_client)

    rows = cred_client.get("/deploy/requests").json()
    deployed = next(row for row in rows if row["status"] == "deployed")
    assert deployed["execution_result"]["outcome"] == "staged"
    assert Path(deployed["execution_result"]["staging_dir"]).is_dir()
