from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.engineering_goal import (
    build_engineering_roles,
    solve_engineering_goal,
)
from agentswarm_agents.solve import build_parser, main


def test_build_engineering_roles_has_four_workers_by_default() -> None:
    roles = build_engineering_roles("abc12345", owner_prefix="solve")
    assert len(roles) == 4
    owners = [owner for _caps, owner in roles]
    assert owners == [
        "solve-coordinator-abc12345",
        "solve-codewriter-abc12345",
        "solve-tester-abc12345",
        "solve-reviewer-abc12345",
    ]


def test_build_engineering_roles_sandbox_includes_builder() -> None:
    roles = build_engineering_roles(
        "abc12345",
        owner_prefix="solve",
        sandbox_tester=True,
        sandbox_builder=True,
    )
    assert len(roles) == 5
    assert roles[2][1] == "solve-builder-abc12345"
    assert roles[2][0] == ["sandbox.build"]
    assert roles[3][0] == ["sandbox.test"]


def test_build_engineering_roles_windows_sandbox_includes_builder() -> None:
    roles = build_engineering_roles(
        "abc12345",
        owner_prefix="solve",
        windows_sandbox_tester=True,
        windows_sandbox_builder=True,
    )
    assert len(roles) == 5
    assert roles[2][0] == ["sandbox.windows.build"]
    assert roles[3][0] == ["sandbox.windows.test"]


@patch("agentswarm_agents.engineering_goal.join_volunteer_threads")
@patch("agentswarm_agents.engineering_goal.wait_for_goal")
@patch("agentswarm_agents.engineering_goal.register_poster_and_create_engineering_goal")
@patch("agentswarm_agents.engineering_goal.start_volunteer_threads")
@patch("agentswarm_agents.engineering_goal.reset_fixture")
@patch("agentswarm_agents.engineering_goal.httpx.Client")
def test_solve_engineering_goal_verified(
    mock_client_cls: MagicMock,
    _reset_fixture: MagicMock,
    mock_start_threads: MagicMock,
    mock_register: MagicMock,
    mock_wait_goal: MagicMock,
    mock_join: MagicMock,
) -> None:
    config_response = MagicMock()
    config_response.raise_for_status.return_value = None
    config_response.json.return_value = {
        "assignment_mode": "dispatch",
        "dispatch": {"long_poll_max_sec": 30},
    }
    client = MagicMock()
    client.get.return_value = config_response
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    mock_client_cls.return_value = client

    ready_barrier = MagicMock()
    mock_start_threads.return_value = ([], [], ready_barrier, {})
    mock_register.return_value = ("poster-1", "goal-xyz")
    mock_wait_goal.return_value = {"status": "verified", "goal_kind": "engineering"}

    result = solve_engineering_goal(
        "https://example.test/api",
        "implement primes",
        fixture="primes",
        model_id="llm-mock-v1",
        owner_prefix="solve",
    )

    assert result["goal_id"] == "goal-xyz"
    assert result["goal_status"] == "verified"
    mock_register.assert_called_once()
    ready_barrier.wait.assert_called_once()
    mock_join.assert_called_once()


def test_solve_cli_parser_fixtures_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["fixtures"])
    assert args.brief == ["fixtures"]


@patch("agentswarm_agents.solve.solve_engineering_goal")
def test_solve_cli_run_brief(mock_solve: MagicMock) -> None:
    mock_solve.return_value = {
        "goal_id": "goal-1",
        "verification_spec": {"fixture": "primes"},
        "brief": "do something",
        "artifact_text": None,
    }
    assert main(["implement primes", "--base-url", "http://localhost/api"]) == 0
    mock_solve.assert_called_once()


def test_solve_engineering_goal_raises_when_not_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        patch("agentswarm_agents.engineering_goal.httpx.Client") as mock_client_cls,
        patch("agentswarm_agents.engineering_goal.start_volunteer_threads") as mock_start,
        patch(
            "agentswarm_agents.engineering_goal.register_poster_and_create_engineering_goal",
            return_value=("p", "g"),
        ),
        patch(
            "agentswarm_agents.engineering_goal.wait_for_goal",
            return_value={"status": "rejected"},
        ),
        patch("agentswarm_agents.engineering_goal.join_volunteer_threads"),
        patch("agentswarm_agents.engineering_goal.reset_fixture"),
    ):
        config_response = MagicMock()
        config_response.raise_for_status.return_value = None
        config_response.json.return_value = {"assignment_mode": "dispatch"}
        client = MagicMock()
        client.get.return_value = config_response
        client.__enter__.return_value = client
        client.__exit__.return_value = None
        mock_client_cls.return_value = client

        ready_barrier = MagicMock()
        mock_start.return_value = ([], [], ready_barrier, {})

        with pytest.raises(RuntimeError, match="not verified"):
            solve_engineering_goal("http://localhost/api", "brief")
