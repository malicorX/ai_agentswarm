from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from agentswarm_platform.models import utc_now_iso


def ensure_moderation_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS moderation_flags (
            flag_id TEXT PRIMARY KEY,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );
        """
    )
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()
    }
    if "quarantined" not in columns:
        conn.execute("ALTER TABLE agents ADD COLUMN quarantined INTEGER NOT NULL DEFAULT 0")
    if "quarantine_reason" not in columns:
        conn.execute("ALTER TABLE agents ADD COLUMN quarantine_reason TEXT")


def list_moderation_flags(
    conn: sqlite3.Connection, *, status: str | None = "open", limit: int = 50
) -> list[dict[str, Any]]:
    if status:
        rows = conn.execute(
            """
            SELECT * FROM moderation_flags
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM moderation_flags
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_flag(row) for row in rows]


def create_flag(
    conn: sqlite3.Connection,
    *,
    subject_type: str,
    subject_id: str,
    reason: str,
    severity: str,
    details: dict[str, Any],
) -> str:
    flag_id = f"flag_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO moderation_flags (
            flag_id, subject_type, subject_id, reason, severity, status,
            details, created_at, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            flag_id,
            subject_type,
            subject_id,
            reason,
            severity,
            "open",
            json.dumps(details),
            utc_now_iso(),
            None,
        ),
    )
    return flag_id


def resolve_flag(conn: sqlite3.Connection, flag_id: str) -> None:
    conn.execute(
        """
        UPDATE moderation_flags
        SET status = ?, resolved_at = ?
        WHERE flag_id = ? AND status = ?
        """,
        ("resolved", utc_now_iso(), flag_id, "open"),
    )


def set_agent_quarantine(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    quarantined: bool,
    reason: str | None,
) -> None:
    conn.execute(
        """
        UPDATE agents
        SET quarantined = ?, quarantine_reason = ?
        WHERE agent_id = ?
        """,
        (1 if quarantined else 0, reason, agent_id),
    )


def is_agent_quarantined(conn: sqlite3.Connection, agent_id: str) -> bool:
    row = conn.execute(
        "SELECT quarantined FROM agents WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    if row is None:
        return False
    return bool(row["quarantined"])


def apply_moderator_action(
    conn: sqlite3.Connection,
    action: dict[str, Any],
) -> dict[str, Any]:
    action_type = action.get("type")
    if action_type == "flag":
        flag_id = create_flag(
            conn,
            subject_type=str(action["subject_type"]),
            subject_id=str(action["subject_id"]),
            reason=str(action.get("reason", "moderator flag")),
            severity=str(action.get("severity", "medium")),
            details=action.get("details") or {},
        )
        return {"type": "flag", "flag_id": flag_id}
    if action_type == "quarantine":
        agent_id = str(action["agent_id"])
        reason = str(action.get("reason", "moderator quarantine"))
        set_agent_quarantine(conn, agent_id=agent_id, quarantined=True, reason=reason)
        flag_id = create_flag(
            conn,
            subject_type="agent",
            subject_id=agent_id,
            reason=reason,
            severity="high",
            details={"action": "quarantine"},
        )
        return {"type": "quarantine", "agent_id": agent_id, "flag_id": flag_id}
    if action_type == "clear_quarantine":
        agent_id = str(action["agent_id"])
        set_agent_quarantine(conn, agent_id=agent_id, quarantined=False, reason=None)
        return {"type": "clear_quarantine", "agent_id": agent_id}
    if action_type == "resolve_flag":
        flag_id = str(action["flag_id"])
        resolve_flag(conn, flag_id)
        return {"type": "resolve_flag", "flag_id": flag_id}
    raise ValueError(f"unknown moderator action type: {action_type}")


def _row_to_flag(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "flag_id": row["flag_id"],
        "subject_type": row["subject_type"],
        "subject_id": row["subject_id"],
        "reason": row["reason"],
        "severity": row["severity"],
        "status": row["status"],
        "details": json.loads(row["details"]),
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
    }
