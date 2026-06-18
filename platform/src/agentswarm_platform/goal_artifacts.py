"""Collect deployable artifact refs from verified engineering goals (D5)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def refs_from_submission_result(result: dict[str, Any] | None) -> list[str]:
    if not isinstance(result, dict):
        return []
    refs: list[str] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        if not isinstance(raw, str):
            return
        cleaned = raw.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            refs.append(cleaned)

    add(result.get("artifact_ref"))
    for nested_key in ("run_artifact", "build_artifact"):
        nested = result.get(nested_key)
        if isinstance(nested, dict):
            add(nested.get("artifact_ref"))
            add(nested.get("log_artifact_ref"))
    return refs


def collect_goal_artifact_refs(conn: sqlite3.Connection, goal_id: str) -> list[str]:
    pattern = f"%{goal_id}%"
    rows = conn.execute(
        """
        SELECT submission_result
        FROM tasks
        WHERE payload LIKE ? AND submission_result IS NOT NULL
        ORDER BY submitted_at ASC, created_at ASC
        """,
        (pattern,),
    ).fetchall()
    refs: list[str] = []
    seen: set[str] = set()
    for row in rows:
        try:
            result = json.loads(row["submission_result"])
        except (json.JSONDecodeError, TypeError):
            continue
        for ref in refs_from_submission_result(result if isinstance(result, dict) else None):
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def select_primary_deploy_artifact_ref(
    refs: list[str],
    goal: dict[str, Any],
) -> str | None:
    spec = goal.get("verification_spec")
    if isinstance(spec, dict):
        override = spec.get("deploy_artifact_ref")
        if isinstance(override, str) and override.strip():
            return override.strip()
    sha_refs = [ref for ref in refs if ref.lower().startswith("sha256:")]
    if sha_refs:
        return sha_refs[-1]
    workspace_ref = goal.get("workspace_ref")
    if isinstance(workspace_ref, str) and workspace_ref.strip():
        return workspace_ref.strip()
    return refs[-1] if refs else None


def snapshot_goal_artifact_refs(conn: sqlite3.Connection, goal_id: str) -> dict[str, Any]:
    from agentswarm_platform.subjective_store import get_creative_goal

    goal = get_creative_goal(conn, goal_id)
    if goal is None:
        raise ValueError("goal not found")
    refs = collect_goal_artifact_refs(conn, goal_id)
    primary = select_primary_deploy_artifact_ref(refs, goal)
    conn.execute(
        """
        UPDATE creative_goals
        SET artifact_refs_json = ?, primary_artifact_ref = ?
        WHERE goal_id = ?
        """,
        (json.dumps(refs), primary, goal_id),
    )
    return {"artifact_refs": refs, "primary_artifact_ref": primary}
