from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from agentswarm_agents.create_task import (
    create_goal_from_spec,
    create_task_from_file,
    format_create_task_output,
    main,
)
from agentswarm_agents.task_file import TaskSpec


def test_format_create_task_output_includes_task_id_alias() -> None:
    text = format_create_task_output(
        {
            "goal_id": "goal-abc",
            "coordinator_task_id": "task-xyz",
            "status": "pending",
        }
    )
    assert "goal_id=goal-abc" in text
    assert "TaskId=goal-abc" in text
    assert "coordinator_task_id=task-xyz" in text
    assert "initial_status=pending" in text


@patch("agentswarm_agents.create_task.goal_auth_headers", return_value={"X-Bootstrap-Token": "t"})
@patch("agentswarm_agents.create_task.generate_keypair", return_value=(object(), object()))
@patch("agentswarm_agents.create_task.public_key_b64", return_value="pub")
@patch("agentswarm_agents.create_task.httpx.Client")
def test_create_goal_from_spec_posts_creative_goal(
    mock_client_cls: MagicMock,
    _pub_b64: MagicMock,
    _keypair: MagicMock,
    _headers: MagicMock,
) -> None:
    register_response = MagicMock()
    register_response.raise_for_status.return_value = None
    register_response.json.return_value = {"agent_id": "poster-1"}

    goal_response = MagicMock()
    goal_response.raise_for_status.return_value = None
    goal_response.json.return_value = {
        "goal_id": "goal-123",
        "coordinator_task_id": "task-456",
        "status": "pending",
    }

    client = MagicMock()
    client.post.side_effect = [register_response, goal_response]
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_client_cls.return_value = client

    spec = TaskSpec(brief="Implement primes.", fixture="primes")
    result = create_goal_from_spec("http://localhost/api", spec)

    assert result["goal_id"] == "goal-123"
    assert result["coordinator_task_id"] == "task-456"
    goal_call = client.post.call_args_list[1]
    payload = goal_call.kwargs["json"]
    assert payload["goal_kind"] == "engineering"
    assert payload["verification_spec"] == {"fixture": "primes", "lab": "engineering-lab"}


@patch("agentswarm_agents.create_task.create_goal_from_spec")
def test_create_task_from_file(mock_create: MagicMock, tmp_path: Path) -> None:
    task_path = tmp_path / "task.txt"
    task_path.write_text("Do the thing.", encoding="utf-8")
    mock_create.return_value = {
        "goal_id": "goal-1",
        "coordinator_task_id": "task-1",
        "status": "pending",
    }
    result = create_task_from_file("http://localhost/api", task_path)
    assert result["goal_id"] == "goal-1"
    mock_create.assert_called_once()


@patch("agentswarm_agents.create_task.create_task_from_file")
def test_create_task_cli_success(mock_create: MagicMock, tmp_path: Path) -> None:
    task_path = tmp_path / "task.txt"
    task_path.write_text("Brief.", encoding="utf-8")
    mock_create.return_value = {
        "goal_id": "goal-cli",
        "coordinator_task_id": "task-cli",
        "status": "pending",
    }
    exit_code = main(["--task-file", str(task_path), "--base-url", "http://localhost/api"])
    assert exit_code == 0


def test_create_task_cli_missing_auth(tmp_path: Path) -> None:
    task_path = tmp_path / "task.txt"
    task_path.write_text("Brief.", encoding="utf-8")
    with patch("agentswarm_agents.create_task.goal_auth_headers", return_value={}):
        exit_code = main(["--task-file", str(task_path), "--base-url", "http://localhost/api"])
    assert exit_code == 1
