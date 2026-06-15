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
            deferred_pool_needs_json TEXT
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
        """
    )
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(creative_goals)").fetchall()
    }
    if "deferred_pool_needs_json" not in columns:
        conn.execute(
            "ALTER TABLE creative_goals ADD COLUMN deferred_pool_needs_json TEXT"
        )


def insert_creative_goal(
    conn: sqlite3.Connection,
    *,
    poster_agent_id: str,
    project_id: str,
    brief: str,
    rubric: list[dict[str, Any]],
    min_reviewers: int,
    pass_threshold: float,
) -> str:
    goal_id = f"goal-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO creative_goals (
            goal_id, poster_agent_id, project_id, brief, rubric_json,
            min_reviewers, pass_threshold, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
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
