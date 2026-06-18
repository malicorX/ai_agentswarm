from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.engineering_goal import build_engineering_roles
from agentswarm_agents.start_task import (
    execute_goal_with_volunteers,
    format_start_task_output,
    main,
    wait_for_team_workers_ready,
)


@patch("agentswarm_agents.start_task.realign_goal_to_team", return_value={"reclaimed_need_ids": [], "redispatched_need_ids": ["n1"]})
@patch("agentswarm_agents.start_task.wait_for_goal")
@patch("agentswarm_agents.start_task.start_engineering_volunteer_threads")
@patch("agentswarm_agents.start_task.validate_dispatch_platform", return_value="llm-mock-v1")
@patch("agentswarm_agents.start_task.httpx.Client")
def test_execute_goal_with_volunteers_verified(
    mock_client_cls: MagicMock,
    _validate: MagicMock,
    mock_start_threads: MagicMock,
    mock_wait_goal: MagicMock,
    _realign: MagicMock,
) -> None:
    config_response = MagicMock()
    config_response.raise_for_status.return_value = None
    config_response.json.return_value = {"assignment_mode": "dispatch"}
    client = MagicMock()
    client.get.return_value = config_response
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_client_cls.return_value = client

    class _Thread:
        def __init__(self) -> None:
            self.is_alive = MagicMock(return_value=False)

        def join(self, timeout: float = 0) -> None:
            return None

    mock_start_threads.return_value = [_Thread(), _Thread()]
    mock_wait_goal.return_value = {
        "status": "verified",
        "goal_kind": "engineering",
        "artifact_text": "2\n3\n5",
    }

    goal = execute_goal_with_volunteers(
        "http://localhost/api",
        "goal-abc",
        wait_for_workers=False,
    )
    assert goal["status"] == "verified"
    _realign.assert_called_once()


@patch("agentswarm_agents.start_task.goal_auth_headers", return_value={})
@patch("agentswarm_agents.start_task.httpx.Client")
def test_wait_for_team_workers_ready_404_fallback(
    mock_client_cls: MagicMock,
    _headers: MagicMock,
) -> None:
    not_found = MagicMock()
    not_found.status_code = 404
    client = MagicMock()
    client.get.return_value = not_found
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_client_cls.return_value = client
    roles = build_engineering_roles("abc", owner_prefix="start")

    with patch("agentswarm_agents.start_task.time.sleep") as mock_sleep:
        body = wait_for_team_workers_ready("http://localhost/api", roles, timeout_sec=1.0, poll_sec=0.01)
    assert body == {}
    mock_sleep.assert_called_once()


@patch("agentswarm_agents.start_task.goal_auth_headers", return_value={})
@patch("agentswarm_agents.start_task.httpx.Client")
def test_wait_for_team_workers_ready(mock_client_cls: MagicMock, _headers: MagicMock) -> None:
    roles = build_engineering_roles("abc", owner_prefix="start")
    caps = {}
    for capabilities, owner in roles:
        capability = capabilities[0]
        caps[capability] = {
            "idle": 1,
            "busy": 0,
            "agents": [{"owner": owner, "status": "idle", "agent_id": f"agent-{owner}"}],
        }
    idle_response = MagicMock()
    idle_response.status_code = 200
    idle_response.raise_for_status.return_value = None
    idle_response.json.return_value = {"capabilities": caps}
    client = MagicMock()
    client.get.return_value = idle_response
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_client_cls.return_value = client

    body = wait_for_team_workers_ready("http://localhost/api", roles, timeout_sec=1.0, poll_sec=0.01)
    assert body["capabilities"]["reviewer"]["idle"] == 1


def test_wait_for_team_workers_ready_times_out() -> None:
    roles = build_engineering_roles("abc", owner_prefix="start")
    with (
        patch("agentswarm_agents.start_task.goal_auth_headers", return_value={}),
        patch("agentswarm_agents.start_task.httpx.Client") as mock_client_cls,
        patch("agentswarm_agents.start_task.time.sleep"),
    ):
        empty_response = MagicMock()
        empty_response.status_code = 200
        empty_response.raise_for_status.return_value = None
        empty_response.json.return_value = {"capabilities": {}}
        client = MagicMock()
        client.get.return_value = empty_response
        client.__enter__.return_value = client
        client.__exit__.return_value = None
        mock_client_cls.return_value = client

        with pytest.raises(RuntimeError, match="not ready"):
            wait_for_team_workers_ready("http://localhost/api", roles, timeout_sec=0.01, poll_sec=0.0)


def test_format_start_task_output() -> None:
    text = format_start_task_output({"status": "verified", "artifact_text": "x"}, goal_id="goal-1")
    assert "goal_id=goal-1" in text
    assert "result=verified" in text


@patch("agentswarm_agents.start_task.execute_goal_with_volunteers")
def test_start_task_cli(mock_execute: MagicMock) -> None:
    mock_execute.return_value = {"status": "verified"}
    assert main(["--goal-id", "goal-xyz", "--base-url", "http://localhost/api"]) == 0
