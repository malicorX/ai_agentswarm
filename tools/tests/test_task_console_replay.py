"""FastAPI tests for task console replay endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tools.task_console.server import app


@pytest.fixture
def console_client() -> TestClient:
    return TestClient(app)


def test_verify_locally_creative(console_client: TestClient) -> None:
    ctx = {
        "goal_id": "goal-creative",
        "goal_kind": "creative",
        "status": "verified",
        "artifact_text": "hello world",
        "verification_spec": {},
    }
    with patch("tools.task_console.server._load_replay_context", return_value=ctx):
        response = console_client.post(
            "/api/goals/goal-creative/verify-locally",
            json={"api_url": "https://example.test/api"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "creative"
    assert body["passed"] is True


def test_workspace_tree_proxy(console_client: TestClient) -> None:
    tree = {
        "mode": "git",
        "workspace_ref": "a" * 40,
        "entries": [{"path": "primes.py", "kind": "file", "size": 12}],
    }
    with patch("tools.task_console.server._load_replay_context", return_value={"goal_id": "goal-x"}):
        with patch("tools.task_console.server.list_workspace_tree", return_value=tree):
            response = console_client.get(
                "/api/goals/goal-x/workspace-tree",
                params={"api_url": "https://example.test/api"},
            )
    assert response.status_code == 200
    assert response.json()["entries"][0]["path"] == "primes.py"


def test_workspace_zip_download(console_client: TestClient) -> None:
    with patch("tools.task_console.server._load_replay_context", return_value={"goal_id": "goal-x"}):
        with patch(
            "tools.task_console.server.build_workspace_zip",
            return_value=(b"PK\x03\x04", "goal-x-deadbeef.zip"),
        ):
            response = console_client.get(
                "/api/goals/goal-x/workspace-zip",
                params={"api_url": "https://example.test/api"},
            )
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert "goal-x-deadbeef.zip" in response.headers.get("content-disposition", "")


def test_goal_outcome_endpoint(console_client: TestClient) -> None:
    trace = {
        "goal_id": "goal-out",
        "status": "verified",
        "goal_kind": "engineering",
        "brief": "do thing",
        "workspace_ref": "a" * 40,
        "steps": [],
    }
    bundle = {"goal_id": "goal-out", "summary": "ok", "deliverables": []}
    with patch("tools.task_console.server._load_replay_context", return_value={}):
        with patch("tools.task_console.server.httpx.Client") as mock_client_cls:
            mock_trace = type("R", (), {"status_code": 200, "json": lambda self: trace, "raise_for_status": lambda self: None})()
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_trace
            with patch("tools.task_console.server.build_outcome_bundle", return_value=bundle):
                response = console_client.get(
                    "/api/goals/goal-out/outcome",
                    params={"api_url": "https://example.test/api"},
                )
    assert response.status_code == 200
    assert response.json()["goal_id"] == "goal-out"


def test_proxy_list_creative_goals(console_client: TestClient) -> None:
    from unittest.mock import MagicMock

    payload = {
        "goals": [
            {
                "goal_id": "goal-old",
                "status": "verified",
                "goal_kind": "engineering",
                "brief_preview": "primes",
                "created_at": "2026-01-01T00:00:00Z",
                "project_id": "default",
            }
        ],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload
    with patch("tools.task_console.server.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.get.return_value = mock_response
        response = console_client.get(
            "/api/proxy/creative/goals",
            params={"api_url": "https://example.test/api", "status": "verified"},
        )
    assert response.status_code == 200
    assert response.json()["goals"][0]["goal_id"] == "goal-old"
