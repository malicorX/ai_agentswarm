from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from agentswarm_platform.models import utc_now_iso


def ensure_version_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_version_history (
            entry_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            version_signature TEXT NOT NULL,
            bump_kind TEXT,
            previous_version TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_version_history_agent
            ON agent_version_history(agent_id, recorded_at);
        """
    )


def record_version_entry(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    version_signature: str,
    bump_kind: str | None = None,
    previous_version: str | None = None,
) -> str:
    entry_id = f"ver_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO agent_version_history (
            entry_id, agent_id, version_signature, bump_kind, previous_version, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            entry_id,
            agent_id,
            version_signature,
            bump_kind,
            previous_version,
            utc_now_iso(),
        ),
    )
    return entry_id


def list_agent_versions(
    conn: sqlite3.Connection, agent_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT entry_id, agent_id, version_signature, bump_kind, previous_version, recorded_at
        FROM agent_version_history
        WHERE agent_id = ?
        ORDER BY recorded_at ASC, rowid ASC
        """,
        (agent_id,),
    ).fetchall()
    return [
        {
            "entry_id": row["entry_id"],
            "agent_id": row["agent_id"],
            "version_signature": row["version_signature"],
            "bump_kind": row["bump_kind"],
            "previous_version": row["previous_version"],
            "recorded_at": row["recorded_at"],
        }
        for row in rows
    ]
