from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from agentswarm_platform.models import utc_now_iso


def ensure_subjective_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS creative_goals (
            goal_id TEXT PRIMARY KEY,
            poster_agent_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            brief TEXT NOT NULL,
            rubric_json TEXT NOT NULL,
            min_reviewers INTEGER NOT NULL,
            pass_threshold REAL NOT NULL,
            status TEXT NOT NULL,
            artifact_text TEXT,
            aggregate_score REAL,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            deferred_pool_needs_json TEXT,
            dispatch_include_owners_json TEXT,
            goal_kind TEXT NOT NULL DEFAULT 'creative',
            verification_spec_json TEXT
        );

        CREATE TABLE IF NOT EXISTS subjective_reviews (
            review_id TEXT PRIMARY KEY,
            goal_id TEXT NOT NULL,
            reviewer_agent_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            scores_json TEXT NOT NULL,
            rationale TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(goal_id, reviewer_agent_id)
        );

        CREATE TABLE IF NOT EXISTS creative_goal_appeals (
            appeal_id TEXT PRIMARY KEY,
            goal_id TEXT NOT NULL UNIQUE,
            filed_by_agent_id TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL,
            resolution_note TEXT,
            filed_at TEXT NOT NULL,
            resolved_at TEXT
        );
        """
    )
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(creative_goals)").fetchall()
    }
    if "deferred_pool_needs_json" not in columns:
        conn.execute(
            "ALTER TABLE creative_goals ADD COLUMN deferred_pool_needs_json TEXT"
        )
    if "dispatch_include_owners_json" not in columns:
        conn.execute(
            "ALTER TABLE creative_goals ADD COLUMN dispatch_include_owners_json TEXT"
        )
    if "goal_kind" not in columns:
        conn.execute(
            "ALTER TABLE creative_goals ADD COLUMN goal_kind TEXT NOT NULL DEFAULT 'creative'"
        )
    if "verification_spec_json" not in columns:
        conn.execute(
            "ALTER TABLE creative_goals ADD COLUMN verification_spec_json TEXT"
        )
    if "workspace_json" not in columns:
        conn.execute("ALTER TABLE creative_goals ADD COLUMN workspace_json TEXT")
    if "workspace_ref" not in columns:
        conn.execute("ALTER TABLE creative_goals ADD COLUMN workspace_ref TEXT")
    if "artifact_refs_json" not in columns:
        conn.execute("ALTER TABLE creative_goals ADD COLUMN artifact_refs_json TEXT")
    if "primary_artifact_ref" not in columns:
        conn.execute("ALTER TABLE creative_goals ADD COLUMN primary_artifact_ref TEXT")


def insert_creative_goal(
    conn: sqlite3.Connection,
    *,
    poster_agent_id: str,
    project_id: str,
    brief: str,
    rubric: list[dict[str, Any]],
    min_reviewers: int,
    pass_threshold: float,
    dispatch_include_owners: list[str] | None = None,
    goal_kind: str = "creative",
    verification_spec: dict[str, Any] | None = None,
    workspace: dict[str, Any] | None = None,
) -> str:
    goal_id = f"goal-{uuid.uuid4().hex[:12]}"
    include_json = (
        json.dumps(dispatch_include_owners) if dispatch_include_owners else None
    )
    verification_json = (
        json.dumps(verification_spec) if verification_spec is not None else None
    )
    workspace_json = json.dumps(workspace) if workspace is not None else None
    conn.execute(
        """
        INSERT INTO creative_goals (
            goal_id, poster_agent_id, project_id, brief, rubric_json,
            min_reviewers, pass_threshold, status, created_at,
            dispatch_include_owners_json, goal_kind, verification_spec_json,
            workspace_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
        """,
        (
            goal_id,
            poster_agent_id,
            project_id,
            brief,
            json.dumps(rubric),
            min_reviewers,
            pass_threshold,
            utc_now_iso(),
            include_json,
            goal_kind,
            verification_json,
            workspace_json,
        ),
    )
    return goal_id


def get_creative_goal(conn: sqlite3.Connection, goal_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM creative_goals WHERE goal_id = ?", (goal_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "goal_id": row["goal_id"],
        "poster_agent_id": row["poster_agent_id"],
        "project_id": row["project_id"],
        "brief": row["brief"],
        "rubric": json.loads(row["rubric_json"]),
        "min_reviewers": int(row["min_reviewers"]),
        "pass_threshold": float(row["pass_threshold"]),
        "status": row["status"],
        "artifact_text": row["artifact_text"],
        "aggregate_score": row["aggregate_score"],
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
        "deferred_pool_needs": (
            json.loads(row["deferred_pool_needs_json"])
            if "deferred_pool_needs_json" in row.keys()
            and row["deferred_pool_needs_json"]
            else []
        ),
        "dispatch_include_owners": (
            json.loads(row["dispatch_include_owners_json"])
            if "dispatch_include_owners_json" in row.keys()
            and row["dispatch_include_owners_json"]
            else []
        ),
        "goal_kind": (
            row["goal_kind"]
            if "goal_kind" in row.keys() and row["goal_kind"]
            else "creative"
        ),
        "verification_spec": (
            json.loads(row["verification_spec_json"])
            if "verification_spec_json" in row.keys()
            and row["verification_spec_json"]
            else None
        ),
        "workspace": (
            json.loads(row["workspace_json"])
            if "workspace_json" in row.keys() and row["workspace_json"]
            else None
        ),
        "workspace_ref": (
            row["workspace_ref"]
            if "workspace_ref" in row.keys() and row["workspace_ref"]
            else None
        ),
        "artifact_refs": (
            json.loads(row["artifact_refs_json"])
            if "artifact_refs_json" in row.keys() and row["artifact_refs_json"]
            else []
        ),
        "primary_artifact_ref": (
            row["primary_artifact_ref"]
            if "primary_artifact_ref" in row.keys() and row["primary_artifact_ref"]
            else None
        ),
    }


def set_goal_deferred_pool_needs(
    conn: sqlite3.Connection,
    goal_id: str,
    deferred_pool_needs: list[dict[str, Any]],
) -> None:
    conn.execute(
        """
        UPDATE creative_goals
        SET deferred_pool_needs_json = ?
        WHERE goal_id = ?
        """,
        (json.dumps(deferred_pool_needs), goal_id),
    )


def clear_goal_deferred_pool_needs(conn: sqlite3.Connection, goal_id: str) -> None:
    conn.execute(
        """
        UPDATE creative_goals
        SET deferred_pool_needs_json = NULL
        WHERE goal_id = ?
        """,
        (goal_id,),
    )


def set_goal_engineering_artifact(
    conn: sqlite3.Connection,
    goal_id: str,
    artifact_text: str,
) -> None:
    conn.execute(
        """
        UPDATE creative_goals
        SET artifact_text = ?, status = 'awaiting_verification'
        WHERE goal_id = ?
        """,
        (artifact_text, goal_id),
    )


def set_goal_workspace_ref(
    conn: sqlite3.Connection,
    goal_id: str,
    workspace_ref: str,
) -> None:
    conn.execute(
        """
        UPDATE creative_goals
        SET workspace_ref = ?
        WHERE goal_id = ?
        """,
        (workspace_ref, goal_id),
    )


def set_goal_artifact(conn: sqlite3.Connection, goal_id: str, artifact_text: str) -> None:
    conn.execute(
        """
        UPDATE creative_goals
        SET artifact_text = ?, status = 'awaiting_reviews'
        WHERE goal_id = ?
        """,
        (artifact_text, goal_id),
    )


def insert_subjective_review(
    conn: sqlite3.Connection,
    *,
    goal_id: str,
    reviewer_agent_id: str,
    task_id: str,
    scores: dict[str, float],
    rationale: str,
) -> str:
    review_id = f"srev-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO subjective_reviews (
            review_id, goal_id, reviewer_agent_id, task_id,
            scores_json, rationale, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            goal_id,
            reviewer_agent_id,
            task_id,
            json.dumps(scores),
            rationale,
            utc_now_iso(),
        ),
    )
    return review_id


def list_reviews_for_goal(conn: sqlite3.Connection, goal_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM subjective_reviews WHERE goal_id = ? ORDER BY created_at ASC",
        (goal_id,),
    ).fetchall()
    return [
        {
            "review_id": row["review_id"],
            "goal_id": row["goal_id"],
            "reviewer_agent_id": row["reviewer_agent_id"],
            "task_id": row["task_id"],
            "scores": json.loads(row["scores_json"]),
            "rationale": row["rationale"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def weighted_review_score(
    scores: dict[str, float], rubric: list[dict[str, Any]]
) -> float:
    total_weight = 0.0
    weighted_sum = 0.0
    for item in rubric:
        dim_id = str(item["id"])
        weight = float(item.get("weight", 1.0))
        if dim_id not in scores:
            raise ValueError(f"missing score for rubric dimension: {dim_id}")
        value = float(scores[dim_id])
        if value < 0 or value > 10:
            raise ValueError(f"score for {dim_id} must be between 0 and 10")
        total_weight += weight
        weighted_sum += weight * value
    if total_weight <= 0:
        raise ValueError("rubric weights must sum above zero")
    return weighted_sum / total_weight


def aggregate_quorum(
    reviews: list[dict[str, Any]],
    rubric: list[dict[str, Any]],
    *,
    pass_threshold: float,
) -> tuple[bool, float]:
    if not reviews:
        return False, 0.0
    per_review = [weighted_review_score(review["scores"], rubric) for review in reviews]
    per_review.sort()
    mid = len(per_review) // 2
    if len(per_review) % 2 == 1:
        aggregate = per_review[mid]
    else:
        aggregate = (per_review[mid - 1] + per_review[mid]) / 2.0
    return aggregate >= pass_threshold, aggregate


def resolve_goal(
    conn: sqlite3.Connection,
    goal_id: str,
    *,
    status: str,
    aggregate_score: float,
) -> None:
    conn.execute(
        """
        UPDATE creative_goals
        SET status = ?, aggregate_score = ?, resolved_at = ?
        WHERE goal_id = ?
        """,
        (status, aggregate_score, utc_now_iso(), goal_id),
    )
    if status == "verified":
        from agentswarm_platform.goal_artifacts import snapshot_goal_artifact_refs

        snapshot_goal_artifact_refs(conn, goal_id)


def get_appeal_for_goal(conn: sqlite3.Connection, goal_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM creative_goal_appeals WHERE goal_id = ?", (goal_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "appeal_id": row["appeal_id"],
        "goal_id": row["goal_id"],
        "filed_by_agent_id": row["filed_by_agent_id"],
        "message": row["message"],
        "status": row["status"],
        "resolution_note": row["resolution_note"],
        "filed_at": row["filed_at"],
        "resolved_at": row["resolved_at"],
    }


def insert_goal_appeal(
    conn: sqlite3.Connection,
    *,
    goal_id: str,
    filed_by_agent_id: str,
    message: str,
) -> str:
    appeal_id = f"appeal-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO creative_goal_appeals (
            appeal_id, goal_id, filed_by_agent_id, message, status, filed_at
        ) VALUES (?, ?, ?, ?, 'pending', ?)
        """,
        (appeal_id, goal_id, filed_by_agent_id, message, utc_now_iso()),
    )
    return appeal_id


def resolve_goal_appeal(
    conn: sqlite3.Connection,
    goal_id: str,
    *,
    status: str,
    resolution_note: str | None,
) -> dict[str, Any]:
    if status not in ("upheld", "overturned"):
        raise ValueError("appeal status must be upheld or overturned")
    row = conn.execute(
        "SELECT * FROM creative_goal_appeals WHERE goal_id = ?", (goal_id,)
    ).fetchone()
    if row is None:
        raise ValueError("no appeal for goal")
    if row["status"] != "pending":
        raise ValueError("appeal is not pending")
    conn.execute(
        """
        UPDATE creative_goal_appeals
        SET status = ?, resolution_note = ?, resolved_at = ?
        WHERE goal_id = ?
        """,
        (status, resolution_note, utc_now_iso(), goal_id),
    )
    return get_appeal_for_goal(conn, goal_id) or {}
