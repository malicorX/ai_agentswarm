from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from agentswarm_platform.assignment_signing import sign_assignment


def ensure_dispatch_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pool_needs (
            need_id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            capability_required TEXT NOT NULL,
            parent_task_id TEXT,
            task_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            constraints_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            assigned_agent_id TEXT,
            lease_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_leases (
            lease_id TEXT PRIMARY KEY,
            need_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            claim_token TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            assignment_signature TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )


def insert_pool_need(
    conn: sqlite3.Connection,
    *,
    role: str,
    capability_required: str,
    task_id: str,
    project_id: str,
    parent_task_id: str | None,
    constraints: dict[str, Any],
) -> str:
    need_id = f"need-{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """
        INSERT INTO pool_needs (
            need_id, role, capability_required, parent_task_id, task_id, project_id,
            constraints_json, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            need_id,
            role,
            capability_required,
            parent_task_id,
            task_id,
            project_id,
            json.dumps(constraints),
            created_at,
        ),
    )
    return need_id


def get_pool_need(conn: sqlite3.Connection, need_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM pool_needs WHERE need_id = ?", (need_id,)).fetchone()


def list_pending_pool_needs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pool_needs WHERE status = 'pending' ORDER BY created_at ASC"
    ).fetchall()


def mark_need_assigned(
    conn: sqlite3.Connection,
    *,
    need_id: str,
    agent_id: str,
    lease_id: str,
) -> None:
    conn.execute(
        """
        UPDATE pool_needs
        SET status = 'assigned', assigned_agent_id = ?, lease_id = ?
        WHERE need_id = ?
        """,
        (agent_id, lease_id, need_id),
    )


def create_assignment_lease(
    conn: sqlite3.Connection,
    *,
    need_id: str,
    agent_id: str,
    task_id: str,
    claim_token: str,
    ttl_minutes: int = 60,
) -> dict[str, Any]:
    lease_id = f"lease-{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = (created_at + timedelta(minutes=ttl_minutes)).replace(microsecond=0)
    sign_payload = {
        "lease_id": lease_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "expires_at": expires_at.isoformat(),
    }
    signature = sign_assignment(sign_payload)
    conn.execute(
        """
        INSERT INTO assignment_leases (
            lease_id, need_id, agent_id, task_id, claim_token,
            expires_at, assignment_signature, created_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lease_id,
            need_id,
            agent_id,
            task_id,
            claim_token,
            expires_at.isoformat(),
            signature,
            created_at.isoformat(),
            "active",
        ),
    )
    return {
        "lease_id": lease_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "claim_token": claim_token,
        "expires_at": expires_at.isoformat(),
        "assignment_signature": signature,
    }


def get_pending_assignment_for_agent(
    conn: sqlite3.Connection, agent_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT l.*, t.task_type, t.capability_required, t.payload, t.project_id
        FROM assignment_leases l
        JOIN tasks t ON t.task_id = l.task_id
        WHERE l.agent_id = ? AND l.status = 'active'
        ORDER BY l.created_at DESC
        LIMIT 1
        """,
        (agent_id,),
    ).fetchone()
    if row is None:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    payload = json.loads(row["payload"]) if row["payload"] else {}
    capsule = payload.get("capsule", payload)
    sign_payload = {
        "lease_id": row["lease_id"],
        "agent_id": row["agent_id"],
        "task_id": row["task_id"],
        "expires_at": row["expires_at"],
    }
    return {
        "lease_id": row["lease_id"],
        "task_id": row["task_id"],
        "task_type": row["task_type"],
        "capability_required": row["capability_required"],
        "project_id": row["project_id"],
        "claim_token": row["claim_token"],
        "expires_at": row["expires_at"],
        "assignment_signature": row["assignment_signature"],
        "capsule": capsule,
        "signature_payload": sign_payload,
    }


def new_claim_token() -> str:
    return secrets.token_urlsafe(32)
