from __future__ import annotations

import sqlite3
from typing import Any


def summarize_owner_clusters(
    conn: sqlite3.Connection,
    *,
    min_agents: int = 5,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if min_agents < 2:
        return []
    rows = conn.execute(
        """
        SELECT owner, COUNT(*) AS agent_count
        FROM agents
        GROUP BY owner
        HAVING COUNT(*) >= ?
        ORDER BY agent_count DESC
        LIMIT ?
        """,
        (min_agents, limit),
    ).fetchall()
    return [
        {"owner": str(row["owner"]), "agent_count": int(row["agent_count"])}
        for row in rows
    ]
