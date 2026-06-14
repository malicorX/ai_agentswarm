from agentswarm_agents.workers.deployer import build_execution_result


def test_build_execution_result_simulated_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AGENTSWARM_DEPLOY_TARGET_URL", raising=False)
    result = build_execution_result(
        {
            "request_id": "deploy_abc",
            "environment": "staging",
            "artifact_ref": "sha-1",
        }
    )
    assert result["outcome"] == "simulated"
    assert result["request_id"] == "deploy_abc"


def test_build_execution_result_with_target(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSWARM_DEPLOY_TARGET_URL", "https://example.pages.dev")
    result = build_execution_result(
        {
            "request_id": "deploy_xyz",
            "environment": "production",
            "artifact_ref": "v1.2.3",
        }
    )
    assert result["outcome"] == "target_configured"
    assert "example.pages.dev" in result["message"]
