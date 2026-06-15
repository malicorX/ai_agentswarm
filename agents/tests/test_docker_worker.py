from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.docker_worker import (
    assignment_signature_payload,
    build_worker_input,
    docker_capsule_executor,
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
        result = run_capsule_in_docker(signed, agent_id="agent-42", image="agentswarm-worker:test")

    assert result == {"text": "from container"}
    args, kwargs = run.call_args
    assert args[0][:4] == ["docker", "run", "--rm", "-i"]
    assert args[0][-1] == "agentswarm-worker:test"
    assert json.loads(kwargs["input"].decode()) == expected_input


def test_docker_capsule_executor_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ASSIGNMENT_SECRET", "test-secret")
    signed = _signed_assignment("agent-99")
    with patch(
        "agentswarm_agents.docker_worker.run_capsule_in_docker",
        return_value={"text": "ok"},
    ) as run:
        executor = docker_capsule_executor("agent-99")
        assert executor(signed) == {"text": "ok"}
        run.assert_called_once()
