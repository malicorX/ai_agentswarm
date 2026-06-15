from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def ensure_presence_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_presence (
            agent_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            model_id TEXT,
            vram_gb REAL,
            load REAL NOT NULL DEFAULT 0,
            client_version TEXT,
            ttl_sec INTEGER NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(agent_presence)").fetchall()}
    if "vram_gb" not in columns:
        conn.execute("ALTER TABLE agent_presence ADD COLUMN vram_gb REAL")


def upsert_presence(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    status: str,
    capabilities: list[str],
    model_id: str | None,
    load: float,
    client_version: str | None,
    ttl_sec: int,
    vram_gb: float | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    conn.execute(
        """
        INSERT INTO agent_presence (
            agent_id, status, capabilities, model_id, vram_gb, load, client_version, ttl_sec, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(agent_id) DO UPDATE SET
            status = excluded.status,
            capabilities = excluded.capabilities,
            model_id = excluded.model_id,
            vram_gb = excluded.vram_gb,
            load = excluded.load,
            client_version = excluded.client_version,
            ttl_sec = excluded.ttl_sec,
            last_seen_at = excluded.last_seen_at
        """,
        (
            agent_id,
            status,
            json.dumps(capabilities),
            model_id,
            vram_gb,
            load,
            client_version,
            ttl_sec,
            now.isoformat(),
        ),
    )
    return {
        "agent_id": agent_id,
        "status": status,
        "capabilities": capabilities,
        "model_id": model_id,
        "vram_gb": vram_gb,
        "load": load,
        "client_version": client_version,
        "ttl_sec": ttl_sec,
        "last_seen_at": now.isoformat(),
    }


def _is_fresh(last_seen_at: str, ttl_sec: int, now: datetime) -> bool:
    seen = datetime.fromisoformat(last_seen_at)
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return seen + timedelta(seconds=ttl_sec) >= now


def list_idle_agents_for_capability(
    conn: sqlite3.Connection,
    capability: str,
    *,
    exclude_owners: set[str],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    resolved_now = now or datetime.now(timezone.utc)
    rows = conn.execute(
        """
        SELECT p.*, a.owner, a.owner_id
        FROM agent_presence p
        JOIN agents a ON a.agent_id = p.agent_id
        WHERE p.status = 'idle'
        """
    ).fetchall()
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if not _is_fresh(row["last_seen_at"], int(row["ttl_sec"]), resolved_now):
            continue
        caps = json.loads(row["capabilities"])
        if capability not in caps:
            continue
        owner = str(row["owner"] or "")
        if owner in exclude_owners:
            continue
        eligible.append(
            {
                "agent_id": row["agent_id"],
                "owner": owner,
                "owner_id": row["owner_id"],
                "model_id": row["model_id"],
                "vram_gb": row["vram_gb"],
                "load": float(row["load"] or 0),
            }
        )
    eligible.sort(key=lambda item: (item["load"], item["agent_id"]))
    return eligible


def set_presence_status(conn: sqlite3.Connection, agent_id: str, status: str) -> None:
    conn.execute(
        "UPDATE agent_presence SET status = ?, last_seen_at = ? WHERE agent_id = ?",
        (
            status,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            agent_id,
        ),
    )
