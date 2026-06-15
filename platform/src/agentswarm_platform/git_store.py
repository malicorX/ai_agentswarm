from __future__ import annotations

import re
import sqlite3
from typing import Any

from agentswarm_platform.models import utc_now_iso

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


def ensure_git_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS git_artifacts (
            submission_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            repo_url TEXT NOT NULL,
            branch TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            forge_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def validate_git_artifact(artifact: dict[str, Any]) -> None:
    repo_url = artifact.get("repo_url")
    branch = artifact.get("branch")
    commit_sha = artifact.get("commit_sha")
    if not isinstance(repo_url, str) or not repo_url.strip():
        raise ValueError("git_artifact.repo_url is required")
    if not isinstance(branch, str) or not branch.strip():
        raise ValueError("git_artifact.branch is required")
    if not isinstance(commit_sha, str) or not _SHA_RE.match(commit_sha.strip()):
        raise ValueError("git_artifact.commit_sha must be a git sha")
    forge_type = artifact.get("forge_type", "git")
    if forge_type not in ("git", "github", "gitlab"):
        raise ValueError("git_artifact.forge_type is invalid")


def insert_git_artifact(
    conn: sqlite3.Connection,
    *,
    submission_id: str,
    task_id: str,
    project_id: str,
    artifact: dict[str, Any],
) -> None:
    validate_git_artifact(artifact)
    conn.execute(
        """
        INSERT INTO git_artifacts (
            submission_id, task_id, project_id, repo_url, branch,
            commit_sha, forge_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            task_id,
            project_id,
            artifact["repo_url"].strip(),
            artifact["branch"].strip(),
            artifact["commit_sha"].strip().lower(),
            str(artifact.get("forge_type", "git")),
            utc_now_iso(),
        ),
    )


def get_git_artifact(conn: sqlite3.Connection, submission_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM git_artifacts WHERE submission_id = ?", (submission_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "submission_id": row["submission_id"],
        "task_id": row["task_id"],
        "project_id": row["project_id"],
        "repo_url": row["repo_url"],
        "branch": row["branch"],
        "commit_sha": row["commit_sha"],
        "forge_type": row["forge_type"],
        "created_at": row["created_at"],
    }
