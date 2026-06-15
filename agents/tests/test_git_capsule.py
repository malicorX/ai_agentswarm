from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agentswarm_platform.git_store import validate_git_artifact


def test_validate_git_artifact_rejects_bad_sha() -> None:
    with pytest.raises(ValueError, match="commit_sha"):
        validate_git_artifact(
            {
                "repo_url": "file:///tmp/repo.git",
                "branch": "agentswarm/task_1",
                "commit_sha": "not-a-sha",
            }
        )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_execute_git_patch_capsule_local_bare_repo(tmp_path: Path) -> None:
    from agentswarm_agents.git_capsule import execute_git_patch_capsule

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

    result = execute_git_patch_capsule(
        {
            "task_id": "task_test123",
            "git": {
                "repo_url": bare.as_uri(),
                "default_branch": "main",
                "forge_type": "git",
            },
            "patch": {
                "file": "README.md",
                "insert": "hello from capsule",
                "marker": "<!-- agentswarm -->",
            },
        }
    )
    assert result["applied"] is True
    assert result["git_artifact"]["branch"] == "agentswarm/task_test123"
    assert len(result["git_artifact"]["commit_sha"]) >= 7
