from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Callable

from agentswarm_platform.credibility import credibility_enabled
from agentswarm_platform.credibility_ledger import get_balance
from agentswarm_platform.deploy_policy import DeployPolicy
from agentswarm_platform.models import TaskStatus, utc_now_iso


def ensure_deploy_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS deploy_requests (
            request_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            environment TEXT NOT NULL,
            artifact_ref TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            required_signoffs INTEGER NOT NULL,
            min_credibility REAL NOT NULL,
            created_at TEXT NOT NULL,
            created_by_owner_id TEXT NOT NULL,
            approved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS deploy_signoffs (
            signoff_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            score_at_signoff REAL NOT NULL,
            task_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(request_id, agent_id)
        );
        """
    )
    request_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(deploy_requests)").fetchall()
    }
    for column, ddl in (
        ("deployed_at", "ALTER TABLE deploy_requests ADD COLUMN deployed_at TEXT"),
        (
            "executed_by_agent_id",
            "ALTER TABLE deploy_requests ADD COLUMN executed_by_agent_id TEXT",
        ),
        (
            "execution_result",
            "ALTER TABLE deploy_requests ADD COLUMN execution_result TEXT",
        ),
        (
            "execute_task_id",
            "ALTER TABLE deploy_requests ADD COLUMN execute_task_id TEXT",
        ),
    ):
        if column not in request_columns:
            conn.execute(ddl)


def reject_deploy_request(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    reason: str,
) -> None:
    ensure_deploy_schema(conn)
    row = conn.execute(
        "SELECT status FROM deploy_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError("deploy request not found")
    if row["status"] != "pending":
        raise ValueError(f"deploy request is {row['status']}")
    conn.execute(
        """
        UPDATE deploy_requests
        SET status = ?, description = COALESCE(description, '') || ?
        WHERE request_id = ?
        """,
        ("rejected", f"\nRejected: {reason}", request_id),
    )


def assert_deploy_signoff_allowed(
    conn: sqlite3.Connection,
    *,
    agent: dict[str, Any],
    agent_id: str,
    project_id: str,
    policy: DeployPolicy,
) -> tuple[str, float]:
    agent_caps = set(agent.get("capabilities") or [])
    eligible = set(policy.signoff_capabilities) & agent_caps
    if not eligible:
        raise ValueError(
            "agent lacks a deploy sign-off capability "
            f"({', '.join(policy.signoff_capabilities)})"
        )
    if credibility_enabled():
        best_cap = max(
            eligible,
            key=lambda cap: get_balance(conn, agent_id, cap, project_id),
        )
        best_score = get_balance(conn, agent_id, best_cap, project_id)
        if best_score < policy.min_credibility:
            raise ValueError(
                "credibility floor not met for deploy sign-off "
                f"(need {policy.min_credibility}, have {best_score})"
            )
        return best_cap, best_score
    return sorted(eligible)[0], 0.0


def insert_deploy_request(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    environment: str,
    artifact_ref: str,
    description: str | None,
    owner_id: str,
    policy: DeployPolicy,
) -> dict[str, Any]:
    ensure_deploy_schema(conn)
    request_id = f"deploy_{uuid.uuid4().hex[:12]}"
    created_at = utc_now_iso()
    conn.execute(
        """
        INSERT INTO deploy_requests (
            request_id, project_id, environment, artifact_ref, description,
            status, required_signoffs, min_credibility, created_at,
            created_by_owner_id, approved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            project_id,
            environment,
            artifact_ref,
            description,
            "pending",
            policy.required_signoffs,
            policy.min_credibility,
            created_at,
            owner_id,
            None,
        ),
    )
    return get_deploy_request(conn, request_id) or {}


def enqueue_deploy_approve_tasks(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    project_id: str,
    policy: DeployPolicy,
    append_audit: Callable[[sqlite3.Connection, str, str | None, dict[str, Any]], None],
    actor_id: str | None,
) -> list[str]:
    ensure_deploy_schema(conn)
    created_at = utc_now_iso()
    capability_required = policy.signoff_capabilities[0]
    task_ids: list[str] = []
    for slot in range(1, policy.required_signoffs + 1):
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        payload = {
            "request_id": request_id,
            "stake_tier": "high",
            "slot": slot,
        }
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, capability_required, status, payload,
                parent_task_id, parent_submission_id, created_at, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                "deploy.approve",
                capability_required,
                TaskStatus.CREATED.value,
                json.dumps(payload),
                None,
                None,
                created_at,
                project_id,
            ),
        )
        task_ids.append(task_id)
        append_audit(
            conn,
            "task.created",
            actor_id,
            {
                "task_id": task_id,
                "task_type": "deploy.approve",
                "request_id": request_id,
                "project_id": project_id,
            },
        )
    return task_ids


def record_deploy_signoff(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    agent_id: str,
    capability: str,
    score: float,
    task_id: str | None,
) -> None:
    ensure_deploy_schema(conn)
    existing = conn.execute(
        "SELECT 1 FROM deploy_signoffs WHERE request_id = ? AND agent_id = ?",
        (request_id, agent_id),
    ).fetchone()
    if existing is not None:
        raise ValueError("agent already signed this deploy request")
    request = conn.execute(
        "SELECT status FROM deploy_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if request is None:
        raise ValueError("deploy request not found")
    if request["status"] != "pending":
        raise ValueError(f"deploy request is {request['status']}")
    signoff_id = f"signoff_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO deploy_signoffs (
            signoff_id, request_id, agent_id, capability, score_at_signoff,
            task_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signoff_id,
            request_id,
            agent_id,
            capability,
            score,
            task_id,
            utc_now_iso(),
        ),
    )


def refresh_deploy_request_status(
    conn: sqlite3.Connection,
    request_id: str,
    *,
    append_audit: Callable[[sqlite3.Connection, str, str | None, dict[str, Any]], None]
    | None = None,
    actor_id: str | None = None,
) -> str:
    ensure_deploy_schema(conn)
    row = conn.execute(
        """
        SELECT required_signoffs, status, project_id, execute_task_id
        FROM deploy_requests
        WHERE request_id = ?
        """,
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError("deploy request not found")
    if row["status"] != "pending":
        return str(row["status"])
    count_row = conn.execute(
        "SELECT COUNT(*) AS n FROM deploy_signoffs WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    signoff_count = int(count_row["n"])
    if signoff_count >= int(row["required_signoffs"]):
        approved_at = utc_now_iso()
        conn.execute(
            """
            UPDATE deploy_requests
            SET status = ?, approved_at = ?
            WHERE request_id = ?
            """,
            ("approved", approved_at, request_id),
        )
        if append_audit is not None and not row["execute_task_id"]:
            enqueue_deploy_execute_task(
                conn,
                request_id=request_id,
                project_id=str(row["project_id"]),
                append_audit=append_audit,
                actor_id=actor_id,
            )
        return "approved"
    return "pending"


def enqueue_deploy_execute_task(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    project_id: str,
    append_audit: Callable[[sqlite3.Connection, str, str | None, dict[str, Any]], None],
    actor_id: str | None,
) -> str:
    ensure_deploy_schema(conn)
    row = conn.execute(
        """
        SELECT status, execute_task_id
        FROM deploy_requests
        WHERE request_id = ?
        """,
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError("deploy request not found")
    if row["status"] != "approved":
        raise ValueError("deploy request is not approved")
    if row["execute_task_id"]:
        return str(row["execute_task_id"])
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    created_at = utc_now_iso()
    payload = {"request_id": request_id, "stake_tier": "medium"}
    conn.execute(
        """
        INSERT INTO tasks (
            task_id, task_type, capability_required, status, payload,
            parent_task_id, parent_submission_id, created_at, project_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            "deploy.execute",
            "deployer",
            TaskStatus.CREATED.value,
            json.dumps(payload),
            None,
            None,
            created_at,
            project_id,
        ),
    )
    conn.execute(
        "UPDATE deploy_requests SET execute_task_id = ? WHERE request_id = ?",
        (task_id, request_id),
    )
    append_audit(
        conn,
        "task.created",
        actor_id,
        {
            "task_id": task_id,
            "task_type": "deploy.execute",
            "request_id": request_id,
            "project_id": project_id,
        },
    )
    return task_id


def record_deploy_execution(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    agent_id: str,
    result: dict[str, Any],
) -> None:
    ensure_deploy_schema(conn)
    row = conn.execute(
        "SELECT status FROM deploy_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError("deploy request not found")
    if row["status"] != "approved":
        raise ValueError(f"deploy request is {row['status']}")
    conn.execute(
        """
        UPDATE deploy_requests
        SET status = ?, deployed_at = ?, executed_by_agent_id = ?,
            execution_result = ?
        WHERE request_id = ?
        """,
        (
            "deployed",
            utc_now_iso(),
            agent_id,
            json.dumps(result),
            request_id,
        ),
    )


def list_deploy_signoffs(conn: sqlite3.Connection, request_id: str) -> list[dict[str, Any]]:
    ensure_deploy_schema(conn)
    rows = conn.execute(
        """
        SELECT signoff_id, request_id, agent_id, capability, score_at_signoff,
               task_id, created_at
        FROM deploy_signoffs
        WHERE request_id = ?
        ORDER BY created_at ASC
        """,
        (request_id,),
    ).fetchall()
    return [
        {
            "signoff_id": row["signoff_id"],
            "request_id": row["request_id"],
            "agent_id": row["agent_id"],
            "capability": row["capability"],
            "score_at_signoff": float(row["score_at_signoff"]),
            "task_id": row["task_id"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_deploy_request(conn: sqlite3.Connection, request_id: str) -> dict[str, Any] | None:
    ensure_deploy_schema(conn)
    row = conn.execute(
        "SELECT * FROM deploy_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    signoffs = list_deploy_signoffs(conn, request_id)
    execution_result: dict[str, Any] | None = None
    raw_execution = row["execution_result"] if "execution_result" in row.keys() else None
    if raw_execution:
        try:
            parsed = json.loads(raw_execution)
            execution_result = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            execution_result = None
    keys = row.keys()
    return {
        "request_id": row["request_id"],
        "project_id": row["project_id"],
        "environment": row["environment"],
        "artifact_ref": row["artifact_ref"],
        "description": row["description"],
        "status": row["status"],
        "required_signoffs": int(row["required_signoffs"]),
        "min_credibility": float(row["min_credibility"]),
        "signoff_count": len(signoffs),
        "signoffs": signoffs,
        "created_at": row["created_at"],
        "created_by_owner_id": row["created_by_owner_id"],
        "approved_at": row["approved_at"],
        "deployed_at": row["deployed_at"] if "deployed_at" in keys else None,
        "executed_by_agent_id": (
            row["executed_by_agent_id"] if "executed_by_agent_id" in keys else None
        ),
        "execution_result": execution_result,
        "execute_task_id": row["execute_task_id"] if "execute_task_id" in keys else None,
    }


def list_deploy_requests(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_deploy_schema(conn)
    query = "SELECT request_id FROM deploy_requests WHERE 1=1"
    params: list[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = get_deploy_request(conn, str(row["request_id"]))
        if item is not None:
            results.append(item)
    return results


def summarize_deploy_requests(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_deploy_schema(conn)
    status_rows = conn.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM deploy_requests
        GROUP BY status
        """
    ).fetchall()
    by_status = {str(row["status"]): int(row["n"]) for row in status_rows}
    pending_signoffs = conn.execute(
        """
        SELECT COUNT(*) AS n FROM tasks
        WHERE task_type = 'deploy.approve' AND status = 'created'
        """
    ).fetchone()
    pending_execute = conn.execute(
        """
        SELECT COUNT(*) AS n FROM tasks
        WHERE task_type = 'deploy.execute' AND status = 'created'
        """
    ).fetchone()
    return {
        "by_status": by_status,
        "pending_signoff_tasks": int(pending_signoffs["n"]),
        "pending_execute_tasks": int(pending_execute["n"]),
    }
