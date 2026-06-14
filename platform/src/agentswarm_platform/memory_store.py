from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from agentswarm_platform.models import utc_now_iso


def ensure_memory_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_entries (
            entry_id TEXT PRIMARY KEY,
            memory_key TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL,
            tags TEXT NOT NULL,
            updated_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def list_memory_entries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT entry_id, memory_key, content, tags, updated_by, created_at, updated_at
        FROM memory_entries
        ORDER BY memory_key ASC
        """
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def get_memory_entry(conn: sqlite3.Connection, memory_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT entry_id, memory_key, content, tags, updated_by, created_at, updated_at
        FROM memory_entries
        WHERE memory_key = ?
        """,
        (memory_key,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_entry(row)


def upsert_memory_entry(
    conn: sqlite3.Connection,
    *,
    memory_key: str,
    content: dict[str, Any],
    tags: list[str] | None,
    updated_by: str | None,
) -> dict[str, Any]:
    now = utc_now_iso()
    tags_json = json.dumps(tags or [])
    existing = conn.execute(
        "SELECT entry_id FROM memory_entries WHERE memory_key = ?", (memory_key,)
    ).fetchone()
    if existing is None:
        entry_id = f"mem_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO memory_entries (
                entry_id, memory_key, content, tags, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                memory_key,
                json.dumps(content),
                tags_json,
                updated_by,
                now,
                now,
            ),
        )
    else:
        entry_id = existing["entry_id"]
        conn.execute(
            """
            UPDATE memory_entries
            SET content = ?, tags = ?, updated_by = ?, updated_at = ?
            WHERE memory_key = ?
            """,
            (json.dumps(content), tags_json, updated_by, now, memory_key),
        )
    row = conn.execute(
        "SELECT * FROM memory_entries WHERE memory_key = ?", (memory_key,)
    ).fetchone()
    assert row is not None
    return _row_to_entry(row)


def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "entry_id": row["entry_id"],
        "key": row["memory_key"],
        "content": json.loads(row["content"]),
        "tags": json.loads(row["tags"]),
        "updated_by": row["updated_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
