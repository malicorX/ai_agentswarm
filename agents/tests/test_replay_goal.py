from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agentswarm_agents.replay_goal import build_workspace_zip, verify_goal_locally


def test_verify_git_goal_uses_host_checkout(tmp_path: Path) -> None:
    repo = tmp_path / "tree"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (repo / "primes.py").write_text("print('ok')\n", encoding="utf-8")
    (tests_dir / "test_primes.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    ctx = {
        "goal_id": "goal-replay",
        "goal_kind": "engineering",
        "status": "verified",
        "workspace_ref": "a" * 40,
        "verification_spec": {"workspace_mode": "git", "fixture": "primes"},
    }
    with patch("agentswarm_agents.replay_goal._checkout_workspace", return_value=(repo, "a" * 40)):
        result = verify_goal_locally(ctx)
    assert result["passed"] is True
    assert result["replay_mode"] == "git_host_cache"


def test_build_workspace_zip_engineering(tmp_path: Path) -> None:
    repo = tmp_path / "tree"
    repo.mkdir(parents=True)
    (repo / "primes.py").write_text("x = 1\n", encoding="utf-8")
    ctx = {
        "goal_id": "goal-zip",
        "goal_kind": "engineering",
        "workspace_ref": "b" * 40,
        "verification_spec": {"workspace_mode": "git"},
    }
    with patch("agentswarm_agents.replay_goal._checkout_workspace", return_value=(repo, "b" * 40)):
        data, filename = build_workspace_zip(ctx)
    assert filename.startswith("goal-zip-")
    assert filename.endswith(".zip")
    assert data[:2] == b"PK"


def test_build_workspace_zip_creative() -> None:
    ctx = {
        "goal_id": "goal-creative",
        "goal_kind": "creative",
        "artifact_text": "hello poem",
    }
    data, filename = build_workspace_zip(ctx)
    assert filename == "goal-creative-artifact.zip"
    assert data[:2] == b"PK"
