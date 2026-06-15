from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from agentswarm_platform.assignment_signing import sign_assignment
from agentswarm_platform.hardware_gates import agent_meets_reviewer_hardware
from agentswarm_platform.presence_store import evict_stale_presence, presence_is_fresh


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


def list_pending_need_ids_for_agent(
    conn: sqlite3.Connection,
    agent_id: str,
    *,
    limit: int = 32,
) -> list[str]:
    """Pending needs an idle agent can take, oldest first."""
    presence = conn.execute(
        "SELECT * FROM agent_presence WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    if presence is None or presence["status"] != "idle":
        return []
    agent = conn.execute(
        "SELECT owner FROM agents WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    if agent is None:
        return []
    owner = str(agent["owner"] or "")
    capabilities = set(json.loads(presence["capabilities"]))
    matched: list[str] = []
    for need in list_pending_pool_needs(conn):
        capability_required = str(need["capability_required"])
        if capability_required not in capabilities:
            continue
        constraints = json.loads(need["constraints_json"])
        include_owners = {str(item) for item in constraints.get("include_owners") or []}
        if include_owners and owner not in include_owners:
            continue
        exclude_owners = {
            str(item)
            for item in constraints.get("exclude_owners")
            or constraints.get("exclude_owner_ids")
            or []
        }
        if owner in exclude_owners:
            continue
        exclude_agents = {
            str(item)
            for item in constraints.get("exclude_agent_ids")
            or constraints.get("exclude_agents")
            or []
        }
        if agent_id in exclude_agents:
            continue
        if capability_required == "reviewer" and not agent_meets_reviewer_hardware(
            model_id=presence["model_id"],
            vram_gb=presence["vram_gb"],
        ):
            continue
        matched.append(str(need["need_id"]))
        if len(matched) >= limit:
            break
    return matched


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


def _reclaim_assignment_lease_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    now_iso: str,
) -> str | None:
    """Reset one active lease; return need_id when the pool need returns to pending."""
    task = conn.execute(
        "SELECT status, claimed_by FROM tasks WHERE task_id = ?",
        (row["task_id"],),
    ).fetchone()
    if task is not None and task["status"] == "claimed":
        conn.execute(
            """
            UPDATE tasks
            SET status = 'created', claimed_by = NULL, claim_token = NULL, claim_deadline = NULL
            WHERE task_id = ? AND status = 'claimed'
            """,
            (row["task_id"],),
        )
    conn.execute(
        "UPDATE assignment_leases SET status = 'expired' WHERE lease_id = ?",
        (row["lease_id"],),
    )
    need = conn.execute(
        "SELECT status, lease_id, assigned_agent_id FROM pool_needs WHERE need_id = ?",
        (row["need_id"],),
    ).fetchone()
    reclaimed_need_id: str | None = None
    if need is not None and need["status"] == "assigned":
        if need["lease_id"] == row["lease_id"] or need["assigned_agent_id"] == row["agent_id"]:
            conn.execute(
                """
                UPDATE pool_needs
                SET status = 'pending', assigned_agent_id = NULL, lease_id = NULL
                WHERE need_id = ?
                """,
                (row["need_id"],),
            )
            reclaimed_need_id = str(row["need_id"])
    conn.execute("DELETE FROM agent_presence WHERE agent_id = ?", (row["agent_id"],))
    return reclaimed_need_id


def reclaim_expired_assignment_leases(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Expire overdue active leases; reset pool needs and claimed tasks for redispatch."""
    resolved_now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    now_iso = resolved_now.isoformat()
    rows = conn.execute(
        """
        SELECT lease_id, need_id, agent_id, task_id
        FROM assignment_leases
        WHERE status = 'active' AND expires_at < ?
        ORDER BY expires_at ASC
        """,
        (now_iso,),
    ).fetchall()
    reclaimed_need_ids: list[str] = []
    for row in rows:
        need_id = _reclaim_assignment_lease_row(conn, row, now_iso=now_iso)
        if need_id is not None:
            reclaimed_need_ids.append(need_id)
    return reclaimed_need_ids


def reclaim_leases_for_stale_presence(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Reclaim active leases held by agents whose presence heartbeat has expired."""
    resolved_now = now or datetime.now(timezone.utc)
    now_iso = resolved_now.replace(microsecond=0).isoformat()
    rows = conn.execute(
        """
        SELECT l.lease_id, l.need_id, l.agent_id, l.task_id
        FROM assignment_leases l
        JOIN agent_presence p ON p.agent_id = l.agent_id
        WHERE l.status = 'active'
        ORDER BY l.created_at ASC
        """
    ).fetchall()
    reclaimed_need_ids: list[str] = []
    for row in rows:
        presence = conn.execute(
            "SELECT last_seen_at, ttl_sec FROM agent_presence WHERE agent_id = ?",
            (row["agent_id"],),
        ).fetchone()
        if presence is None:
            continue
        if presence_is_fresh(
            str(presence["last_seen_at"]),
            int(presence["ttl_sec"]),
            now=resolved_now,
        ):
            continue
        need_id = _reclaim_assignment_lease_row(conn, row, now_iso=now_iso)
        if need_id is not None:
            reclaimed_need_ids.append(need_id)
    return reclaimed_need_ids


def reconcile_claimed_tasks_without_active_lease(
    conn: sqlite3.Connection,
) -> list[str]:
    """Reset assignment-only tasks stuck in claimed without an active lease."""
    rows = conn.execute(
        """
        SELECT task_id
        FROM tasks
        WHERE status = 'claimed'
          AND assignment_only = 1
          AND NOT EXISTS (
              SELECT 1 FROM assignment_leases
              WHERE task_id = tasks.task_id AND status = 'active'
          )
        """
    ).fetchall()
    reconciled: list[str] = []
    for row in rows:
        task_id = str(row["task_id"])
        conn.execute(
            """
            UPDATE tasks
            SET status = 'created', claimed_by = NULL, claim_token = NULL, claim_deadline = NULL
            WHERE task_id = ? AND status = 'claimed'
            """,
            (task_id,),
        )
        conn.execute(
            """
            UPDATE pool_needs
            SET status = 'pending', assigned_agent_id = NULL, lease_id = NULL
            WHERE task_id = ? AND status = 'assigned'
            """,
            (task_id,),
        )
        reconciled.append(task_id)
    return reconciled


def prepare_pool_need_for_dispatch(conn: sqlite3.Connection, need_id: str) -> None:
    """Heal orphaned assignment state so a pending pool need can be dispatched."""
    need = get_pool_need(conn, need_id)
    if need is None:
        return
    task_id = str(need["task_id"])
    active = conn.execute(
        """
        SELECT 1 FROM assignment_leases
        WHERE task_id = ? AND status = 'active'
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    if active is not None:
        return
    conn.execute(
        """
        UPDATE tasks
        SET status = 'created', claimed_by = NULL, claim_token = NULL, claim_deadline = NULL
        WHERE task_id = ? AND status = 'claimed' AND assignment_only = 1
        """,
        (task_id,),
    )
    conn.execute(
        """
        UPDATE pool_needs
        SET status = 'pending', assigned_agent_id = NULL, lease_id = NULL
        WHERE task_id = ? AND status = 'assigned'
        """,
        (task_id,),
    )


def reconcile_assigned_pool_needs_without_active_lease(
    conn: sqlite3.Connection,
) -> list[str]:
    """Return assigned needs to pending when their lease is missing or no longer active."""
    rows = conn.execute(
        """
        SELECT need_id, lease_id, task_id, assigned_agent_id
        FROM pool_needs
        WHERE status = 'assigned'
        """
    ).fetchall()
    reconciled: list[str] = []
    for row in rows:
        lease_id = row["lease_id"]
        active = None
        if lease_id:
            active = conn.execute(
                """
                SELECT 1 FROM assignment_leases
                WHERE lease_id = ? AND status = 'active'
                """,
                (lease_id,),
            ).fetchone()
        if active is not None:
            continue
        conn.execute(
            """
            UPDATE pool_needs
            SET status = 'pending', assigned_agent_id = NULL, lease_id = NULL
            WHERE need_id = ?
            """,
            (row["need_id"],),
        )
        task = conn.execute(
            "SELECT status, claimed_by FROM tasks WHERE task_id = ?",
            (row["task_id"],),
        ).fetchone()
        if task is not None and task["status"] == "claimed":
            conn.execute(
                """
                UPDATE tasks
                SET status = 'created', claimed_by = NULL, claim_token = NULL, claim_deadline = NULL
                WHERE task_id = ? AND status = 'claimed'
                """,
                (row["task_id"],),
            )
        reconciled.append(str(row["need_id"]))
    return reconciled


def maintain_dispatch_pool(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> dict[str, int | list[str]]:
    """Expire leases, reclaim stale agents, and evict dead presence rows."""
    expired = reclaim_expired_assignment_leases(conn, now=now)
    stale = reclaim_leases_for_stale_presence(conn, now=now)
    reconciled_needs = reconcile_assigned_pool_needs_without_active_lease(conn)
    reconciled_tasks = reconcile_claimed_tasks_without_active_lease(conn)
    evicted = evict_stale_presence(conn, now=now)
    return {
        "expired_need_ids": expired,
        "stale_need_ids": stale,
        "reconciled_need_ids": reconciled_needs,
        "reconciled_task_ids": reconciled_tasks,
        "evicted_presence": evicted,
    }


def get_pending_assignment_for_agent(
    conn: sqlite3.Connection, agent_id: str
) -> dict[str, Any] | None:
    maintain_dispatch_pool(conn)
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
