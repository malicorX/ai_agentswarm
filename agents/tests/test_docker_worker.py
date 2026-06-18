from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.docker_worker import (
    assignment_signature_payload,
    build_worker_input,
    docker_capsule_executor,
    resolve_docker_executor,
    run_capsule_in_docker,
    verify_assignment_signature,
)
from agentswarm_platform.assignment_signing import sign_assignment


ASSIGNMENT = {
    "lease_id": "lease-test",
    "task_id": "task-test",
    "task_type": "creative.text",
    "expires_at": "2030-01-01T00:00:00+00:00",
    "claim_token": "claim",
    "capsule": {"brief": "haiku about sandboxes"},
}


def _signed_assignment(agent_id: str) -> dict:
    payload = assignment_signature_payload(ASSIGNMENT, agent_id)
    return {**ASSIGNMENT, "assignment_signature": sign_assignment(payload)}


def test_execute_capsule_creative_text() -> None:
    result = execute_capsule(
        {"task_type": "creative.text", "capsule": {"brief": "winter"}}
    )
    assert "text" in result
    assert "winter" in result["text"]
    assert "Container poem" in result["text"]


def test_verify_assignment_signature_rejects_bad_sig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    bad = {**ASSIGNMENT, "assignment_signature": "deadbeef"}
    with pytest.raises(ValueError, match="invalid or missing assignment signature"):
        verify_assignment_signature(bad, "agent-1")


def test_run_capsule_in_docker_invokes_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    signed = _signed_assignment("agent-42")
    expected_input = build_worker_input(signed)
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({"text": "from container"}).encode()
    mock_proc.stderr = b""

    with patch("agentswarm_agents.docker_worker.subprocess.run", return_value=mock_proc) as run:
        result = run_capsule_in_docker(
            signed,
            agent_id="agent-42",
            image="agentswarm-worker:test",
        )

    assert result == {"text": "from container"}
    args, kwargs = run.call_args
    docker_args = args[0]
    assert docker_args[:4] == ["docker", "run", "--rm", "-i"]
    assert docker_args[-1] == "agentswarm-worker:test"
    assert json.loads(kwargs["input"].decode()) == expected_input


def test_run_capsule_in_docker_mounts_model_weights(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    signed = _signed_assignment("agent-42")
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"weights")
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({"text": "llm"}).encode()
    mock_proc.stderr = b""

    with patch("agentswarm_agents.docker_worker.subprocess.run", return_value=mock_proc) as run:
        run_capsule_in_docker(
            signed,
            agent_id="agent-42",
            image="agentswarm-worker:test",
            model_path=model_file,
            model_entry={"id": "docker/qwen2.5-coder-3b"},
        )

    docker_args = run.call_args.args[0]
    mount = next(arg for arg in docker_args if isinstance(arg, str) and ":ro" in arg and "model.gguf" in arg)
    assert str(model_file.resolve()) in mount
    assert "AGENTSWARM_MODEL_PATH=/models/weights/model.gguf" in docker_args
    assert "AGENTSWARM_ENGINEERING_LLM=1" in docker_args


def test_docker_capsule_executor_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    signed = _signed_assignment("agent-99")
    with patch(
        "agentswarm_agents.docker_worker.run_capsule_in_docker",
        return_value={"text": "ok"},
    ) as run:
        executor = resolve_docker_executor(
            "agent-99",
            model_entry={"id": "llm-docker-worker-v1", "runtime": "docker"},
            default_image="agentswarm-worker:dev",
            model_path=None,
        )
        assert executor(signed) == {"text": "ok"}
        run.assert_called_once()
