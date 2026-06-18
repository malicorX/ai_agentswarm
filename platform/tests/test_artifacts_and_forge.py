from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from agentswarm_platform.artifact_store import (
    enrich_sandbox_tester_result,
    load_artifact_blob,
    normalize_digest_ref,
    store_artifact_blob,
)
from agentswarm_platform.forge_store import (
    forge_credentials_for_assignment,
    goal_branch_prefix,
    mint_goal_forge_credential,
)
from agentswarm_platform.goal_trace import pipeline_phase
from agentswarm_platform.main import app
from agentswarm_platform.store import Store


def test_pipeline_phase_labels() -> None:
    assert pipeline_phase("codewriter.patch") == "code"
    assert pipeline_phase("tester.run") == "test"
    assert pipeline_phase("coordinator.decompose") == "plan"


def test_artifact_store_roundtrip(tmp_path) -> None:
    payload = b"hello artifact blob"
    stored = store_artifact_blob(payload, tmp_path)
    assert stored["artifact_ref"].startswith("sha256:")
    assert stored["cached"] is False
    again = store_artifact_blob(payload, tmp_path)
    assert again["artifact_ref"] == stored["artifact_ref"]
    assert again["cached"] is True
    loaded = load_artifact_blob(str(stored["artifact_ref"]), tmp_path)
    assert loaded == payload


def test_normalize_digest_ref() -> None:
    assert normalize_digest_ref("sha256:" + "a" * 64) == "sha256:" + "a" * 64


def test_enrich_sandbox_tester_result(tmp_path) -> None:
    result = enrich_sandbox_tester_result(
        {
            "passed": True,
            "sandbox": True,
            "stdout": "pytest ok\n",
            "stderr": "",
            "run_artifact": {"stdout_digest": "abc"},
        },
        sandbox_host_owner="sparky2-tester",
        artifacts_dir=tmp_path,
    )
    assert result["sandbox_host_owner"] == "sparky2-tester"
    ref = result["run_artifact"]["log_artifact_ref"]
    assert ref.startswith("sha256:")
    assert load_artifact_blob(ref, tmp_path).decode("utf-8").startswith("=== stdout ===")


def test_enrich_sandbox_build_result_sets_host_without_logs(tmp_path) -> None:
    result = enrich_sandbox_tester_result(
        {
            "passed": True,
            "sandbox": True,
            "stdout": "",
            "stderr": "",
            "build_artifact": {"passed": True},
        },
        sandbox_host_owner="sparky2-builder",
        artifacts_dir=tmp_path,
    )
    assert result["sandbox_host_owner"] == "sparky2-builder"
    assert result["build_artifact"]["sandbox_host_owner"] == "sparky2-builder"
    assert "log_artifact_ref" not in result["build_artifact"]


def test_forge_mint_and_envelope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSWARM_FORGE_MINT_KEYS", "1")
    store = Store(tmp_path / "forge.db")
    with store._conn() as conn:
        cred = mint_goal_forge_credential(
            conn,
            goal_id="goal-test123",
            repo_url="root@host:/repo.git",
        )
    assert cred["branch_prefix"] == goal_branch_prefix("goal-test123")
    envelope = forge_credentials_for_assignment(
        cred,
        lease_expires_at="2026-01-01T00:00:00+00:00",
    )
    assert envelope["type"] == "ssh_deploy_key"
    assert envelope["private_key_pem"]
    assert envelope["allowed_branches"]


def test_forge_deploy_key_install(tmp_path, monkeypatch) -> None:
    from agentswarm_platform.forge_deploy_keys import (
        bare_repo_path_from_url,
        install_forge_deploy_public_key,
    )

    assert bare_repo_path_from_url("root@host:/var/lib/git/primes.git") == "/var/lib/git/primes.git"

    auth_keys = tmp_path / "authorized_keys"
    shell = tmp_path / "forge_git_shell.sh"
    shell.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("AGENTSWARM_FORGE_AUTH_KEYS", str(auth_keys))
    monkeypatch.setenv("AGENTSWARM_FORGE_GIT_SHELL", str(shell))

    cred = {
        "credential_id": "cred-abc",
        "public_key_openssh": "ssh-ed25519 AAAATEST comment",
        "repo_url": "root@theebie:/var/lib/agentswarm/git-workspaces/primes.git",
    }
    assert install_forge_deploy_public_key(cred) is True
    text = auth_keys.read_text(encoding="utf-8")
    assert "# agentswarm-forge:cred-abc" in text
    assert "primes.git" in text
    assert install_forge_deploy_public_key(cred) is False


def test_artifacts_api(tmp_path, monkeypatch) -> None:
    db = tmp_path / "api.db"
    monkeypatch.setenv("AGENTSWARM_DB", str(db))
    monkeypatch.setenv("AGENTSWARM_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "test-bootstrap")
    from agentswarm_platform import main as main_module

    main_module.store = Store(db)
    client = TestClient(main_module.app)
    body = b"log bundle bytes"
    post = client.post(
        "/artifacts",
        content=body,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Bootstrap-Token": "test-bootstrap",
        },
    )
    assert post.status_code == 200
    artifact_ref = post.json()["artifact_ref"]
    assert post.json().get("cached") is False
    post2 = client.post(
        "/artifacts",
        content=body,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Bootstrap-Token": "test-bootstrap",
        },
    )
    assert post2.status_code == 200
    assert post2.json()["artifact_ref"] == artifact_ref
    assert post2.json().get("cached") is True
    get = client.get(
        f"/artifacts/{artifact_ref}",
        headers={"X-Bootstrap-Token": "test-bootstrap"},
    )
    assert get.status_code == 200
    assert base64.b64decode(get.json()["content_base64"]) == body
