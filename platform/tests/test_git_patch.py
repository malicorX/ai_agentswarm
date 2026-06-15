from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_platform.crypto import sign_payload
from test_task_flow import register_agent


@pytest.fixture
def dispatch_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_MODE", "dispatch")
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-dispatch-secret")
    return client


@pytest.fixture
def bare_repo(tmp_path: Path) -> str:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    bare = tmp_path / "remote.git"
    work = tmp_path / "seed"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True)
    subprocess.run(["git", "clone", str(bare), str(work)], check=True)
    subprocess.run(["git", "config", "user.email", "test@agentswarm.local"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "AgentSwarm Test"], cwd=work, check=True)
    (work / "README.md").write_text("# demo\n<!-- agentswarm -->\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=work, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=work, check=True)
    return bare.as_uri()


def _presence(client: TestClient, agent_id: str, capabilities: list[str]) -> None:
    response = client.post(
        f"/agents/{agent_id}/presence",
        json={"status": "idle", "capabilities": capabilities, "ttl_sec": 120},
    )
    assert response.status_code == 200


def test_configure_project_repo(dispatch_client: TestClient, bare_repo: str) -> None:
    response = dispatch_client.patch(
        "/projects/default/repo",
        json={
            "repo_url": bare_repo,
            "default_branch": "main",
            "forge_type": "git",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["repo_url"] == bare_repo
    assert body["default_branch"] == "main"


@pytest.mark.parametrize("forge_type", ["github", "gitlab"])
def test_configure_project_repo_forge_labels(
    dispatch_client: TestClient, bare_repo: str, forge_type: str
) -> None:
    response = dispatch_client.patch(
        "/projects/default/repo",
        json={
            "repo_url": bare_repo,
            "default_branch": "main",
            "forge_type": forge_type,
        },
    )
    assert response.status_code == 200
    assert response.json()["forge_type"] == forge_type


def test_git_patch_assignment_e2e(dispatch_client: TestClient, bare_repo: str) -> None:
    dispatch_client.patch(
        "/projects/default/repo",
        json={"repo_url": bare_repo, "default_branch": "main", "forge_type": "git"},
    )
    coder_id, coder_priv = register_agent(dispatch_client, ["codewriter"], owner="coder-owner")
    reviewer_id, _ = register_agent(dispatch_client, ["reviewer"], owner="reviewer-owner")
    _presence(dispatch_client, coder_id, ["codewriter"])

    create = dispatch_client.post(
        "/projects/default/git/patches",
        json={
            "file": "README.md",
            "insert": "patched by agentswarm",
            "marker": "<!-- agentswarm -->",
        },
    )
    assert create.status_code == 200
    assert create.json()["assigned"] is True

    assignment = dispatch_client.get(f"/agents/{coder_id}/assignments/pending").json()
    assert assignment is not None
    assert assignment["task_type"] == "codewriter.patch"

    result = execute_capsule(assignment)
    signature = sign_payload(coder_priv, {"task_id": assignment["task_id"], "result": result})
    submit = dispatch_client.post(
        "/tasks/submit",
        json={
            "claim_token": assignment["claim_token"],
            "result": result,
            "signature": signature,
        },
    )
    assert submit.status_code == 200
    submission_id = submit.json()["submission_id"]

    artifact = dispatch_client.get(f"/submissions/{submission_id}/git-artifact")
    assert artifact.status_code == 200
    body = artifact.json()
    assert body["branch"].startswith("agentswarm/task_")
    assert len(body["commit_sha"]) >= 7
    assert body["repo_url"] == bare_repo

    tester_id, tester_priv = register_agent(dispatch_client, ["tester"], owner="tester-owner")
    tester_poll = dispatch_client.get(
        "/tasks/poll", params={"agent_id": tester_id, "capability": "tester"}
    ).json()
    assert tester_poll
    tester_task_id = tester_poll[0]["task_id"]
    claim = dispatch_client.post(
        f"/tasks/{tester_task_id}/claim",
        json={"agent_id": tester_id},
    )
    assert claim.status_code == 200
    tester_token = claim.json()["claim_token"]
    tester_result = {"passed": True, "tests_run": 1}
    tester_submit = dispatch_client.post(
        "/tasks/submit",
        json={
            "claim_token": tester_token,
            "result": tester_result,
            "signature": sign_payload(
                tester_priv,
                {"task_id": tester_task_id, "result": tester_result},
            ),
        },
    )
    assert tester_submit.status_code == 200

    reviewer_tasks = dispatch_client.get(
        "/tasks/poll", params={"agent_id": reviewer_id, "capability": "reviewer"}
    ).json()
    assert reviewer_tasks
    reviewer_task = reviewer_tasks[0]
    assert reviewer_task["payload"].get("git_artifact") is not None
    assert reviewer_task["payload"]["git_artifact"]["commit_sha"] == body["commit_sha"]
