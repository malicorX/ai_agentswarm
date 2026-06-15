from __future__ import annotations

import json
import sqlite3
from typing import Any

from agentswarm_platform.credibility_ledger import apply_parallel_group_credibility
from agentswarm_platform.replication import (
    evaluate_quorum,
    result_fingerprint,
    shared_replication_payload,
    validate_parallel_result,
)


def ensure_replication_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS replication_groups (
            group_id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            capability_required TEXT NOT NULL,
            payload TEXT NOT NULL,
            slots INTEGER NOT NULL,
            quorum INTEGER NOT NULL,
            status TEXT NOT NULL,
            winning_fingerprint TEXT,
            winning_result TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            parallel_kind TEXT NOT NULL DEFAULT 'replication',
            good_attempt_mint REAL NOT NULL DEFAULT 0
        );
        """
    )
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(replication_groups)").fetchall()
    }
    if "parallel_kind" not in columns:
        conn.execute(
            "ALTER TABLE replication_groups ADD COLUMN parallel_kind TEXT NOT NULL DEFAULT 'replication'"
        )
    if "good_attempt_mint" not in columns:
        conn.execute(
            "ALTER TABLE replication_groups ADD COLUMN good_attempt_mint REAL NOT NULL DEFAULT 0"
        )
    task_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    if "replication_group_id" not in task_columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN replication_group_id TEXT")
    if "replication_slot" not in task_columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN replication_slot INTEGER")


def get_replication_group(
    conn: sqlite3.Connection, group_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM replication_groups WHERE group_id = ?", (group_id,)
    ).fetchone()
    if row is None:
        return None
    keys = row.keys()
    tasks = conn.execute(
        """
        SELECT task_id, status, replication_slot, claimed_by,
               submission_result, submission_id
        FROM tasks
        WHERE replication_group_id = ?
        ORDER BY replication_slot ASC
        """,
        (group_id,),
    ).fetchall()
    submissions = []
    for task in tasks:
        if task["submission_result"]:
            submissions.append(
                {
                    "task_id": task["task_id"],
                    "agent_id": task["claimed_by"],
                    "slot": task["replication_slot"],
                    "result": json.loads(task["submission_result"]),
                }
            )
    return {
        "group_id": row["group_id"],
        "task_type": row["task_type"],
        "capability_required": row["capability_required"],
        "payload": json.loads(row["payload"]),
        "slots": row["slots"],
        "quorum": row["quorum"],
        "status": row["status"],
        "parallel_kind": row["parallel_kind"] if "parallel_kind" in keys else "replication",
        "good_attempt_mint": float(row["good_attempt_mint"])
        if "good_attempt_mint" in keys
        else 0.0,
        "winning_result": json.loads(row["winning_result"])
        if row["winning_result"]
        else None,
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
        "tasks": [
            {
                "task_id": task["task_id"],
                "slot": task["replication_slot"],
                "status": task["status"],
                "agent_id": task["claimed_by"],
            }
            for task in tasks
        ],
        "submissions": submissions,
        "fingerprint_counts": _fingerprint_counts(row["task_type"], submissions),
    }


def _fingerprint_counts(
    task_type: str, submissions: list[dict[str, Any]]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in submissions:
        fp = result_fingerprint(task_type, item["result"])
        counts[fp] = counts.get(fp, 0) + 1
    return counts


def record_replication_submit(
    conn: sqlite3.Connection,
    *,
    group_id: str,
    task_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    validate_parallel_result(task_type, payload, result)
    group = conn.execute(
        "SELECT * FROM replication_groups WHERE group_id = ?", (group_id,)
    ).fetchone()
    if group is None:
        raise ValueError("replication group not found")
    if group["status"] != "pending":
        return {"status": group["status"]}

    rows = conn.execute(
        """
        SELECT submission_result FROM tasks
        WHERE replication_group_id = ? AND submission_result IS NOT NULL
        """,
        (group_id,),
    ).fetchall()
    submissions = [{"result": json.loads(row["submission_result"])} for row in rows]
    evaluation = evaluate_quorum(
        task_type=task_type,
        submissions=submissions,
        quorum=int(group["quorum"]),
        slots=int(group["slots"]),
    )
    if evaluation.status == "pending":
        return {"status": "pending", "fingerprint_counts": evaluation.counts}

    from agentswarm_platform.models import utc_now_iso

    keys = group.keys()
    good_attempt_mint = (
        float(group["good_attempt_mint"]) if "good_attempt_mint" in keys else 0.0
    )
    resolved_at = utc_now_iso()
    if evaluation.status == "quorum_met":
        conn.execute(
            """
            UPDATE replication_groups
            SET status = ?, winning_fingerprint = ?, winning_result = ?, resolved_at = ?
            WHERE group_id = ?
            """,
            (
                "quorum_met",
                evaluation.winning_fingerprint,
                json.dumps(evaluation.winning_result),
                resolved_at,
                group_id,
            ),
        )
        _finalize_replication_tasks(
            conn,
            group_id=group_id,
            task_type=task_type,
            winning_fingerprint=evaluation.winning_fingerprint,
            disputed=False,
            good_attempt_mint=good_attempt_mint,
        )
        return {
            "status": "quorum_met",
            "winning_result": evaluation.winning_result,
            "fingerprint_counts": evaluation.counts,
        }

    conn.execute(
        """
        UPDATE replication_groups
        SET status = ?, resolved_at = ?
        WHERE group_id = ?
        """,
        ("disputed", resolved_at, group_id),
    )
    _finalize_replication_tasks(
        conn,
        group_id=group_id,
        task_type=task_type,
        winning_fingerprint=None,
        disputed=True,
        good_attempt_mint=good_attempt_mint,
    )
    return {"status": "disputed", "fingerprint_counts": evaluation.counts}


def _finalize_replication_tasks(
    conn: sqlite3.Connection,
    *,
    group_id: str,
    task_type: str,
    winning_fingerprint: str | None,
    disputed: bool,
    good_attempt_mint: float,
) -> None:
    from agentswarm_platform.models import TaskStatus

    tasks = conn.execute(
        """
        SELECT task_id, status, submission_result FROM tasks
        WHERE replication_group_id = ?
        """,
        (group_id,),
    ).fetchall()
    for task in tasks:
        if task["status"] in (
            TaskStatus.VERIFIED.value,
            TaskStatus.REJECTED.value,
        ):
            continue
        if task["submission_result"]:
            result = json.loads(task["submission_result"])
            fp = result_fingerprint(task_type, result)
            if disputed:
                new_status = TaskStatus.REJECTED.value
            elif fp == winning_fingerprint:
                new_status = TaskStatus.VERIFIED.value
            else:
                new_status = TaskStatus.REJECTED.value
        else:
            new_status = TaskStatus.REJECTED.value
        conn.execute(
            "UPDATE tasks SET status = ? WHERE task_id = ?",
            (new_status, task["task_id"]),
        )

    apply_parallel_group_credibility(
        conn,
        group_id=group_id,
        task_type=task_type,
        winning_fingerprint=winning_fingerprint,
        disputed=disputed,
        good_attempt_mint=good_attempt_mint,
    )


def agent_already_in_group(
    conn: sqlite3.Connection, group_id: str, agent_id: str
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM tasks
        WHERE replication_group_id = ? AND claimed_by = ?
        """,
        (group_id, agent_id),
    ).fetchone()
    return row is not None
