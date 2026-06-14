from pathlib import Path

import pytest

from agentswarm_agents.workers.deployer import build_execution_result, run_deploy_hooks


def test_build_execution_result_simulated_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_DEPLOY_STAGING", raising=False)
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


def test_build_execution_result_with_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_DEPLOY_TARGET_URL", "https://example.pages.dev")
    result = build_execution_result(
        {
            "request_id": "deploy_xyz",
            "environment": "production",
            "artifact_ref": "v1.2.3",
        },
        hook_details={"target_url": "https://example.pages.dev"},
    )
    assert result["outcome"] == "target_configured"
    assert "example.pages.dev" in result["message"]


def test_staging_hook_stages_pilot_site(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = Path(__file__).resolve().parents[2]
    output = tmp_path / "staged"
    monkeypatch.setenv("AGENTSWARM_REPO_ROOT", str(repo))
    monkeypatch.setenv("AGENTSWARM_DEPLOY_STAGING", "1")
    monkeypatch.setenv("AGENTSWARM_PILOT_STAGING_DIR", str(output))

    details = run_deploy_hooks(
        {
            "request_id": "deploy_stage",
            "environment": "staging",
            "artifact_ref": "sha-stage",
        }
    )
    assert details["hook"] == "stage_pilot_site"
    assert Path(details["staging_dir"]).exists()
    assert (Path(details["staging_dir"]) / "index.html").is_file()
    assert (Path(details["staging_dir"]) / "dashboard" / "index.html").is_file()

    result = build_execution_result(
        {
            "request_id": "deploy_stage",
            "environment": "staging",
            "artifact_ref": "sha-stage",
        },
        hook_details=details,
    )
    assert result["outcome"] == "staged"
