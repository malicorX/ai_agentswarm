from __future__ import annotations

import os
import sqlite3

import agentswarm_platform.credibility as credibility

QUARANTINE_PENALTY = float(os.environ.get("AGENTSWARM_OWNER_PENALTY_QUARANTINE", "5"))
CANARY_PENALTY = float(os.environ.get("AGENTSWARM_OWNER_PENALTY_CANARY", "2"))
FLAG_HIGH_PENALTY = float(os.environ.get("AGENTSWARM_OWNER_PENALTY_FLAG_HIGH", "3"))


def _penalty_max() -> float:
    return float(
        os.environ.get("AGENTSWARM_OWNER_PENALTY_MAX", str(credibility.INITIAL_SCORE))
    )


def ensure_owner_anchoring_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(owners)").fetchall()
    }
    if "penalty_score" not in columns:
        conn.execute(
            "ALTER TABLE owners ADD COLUMN penalty_score REAL NOT NULL DEFAULT 0"
        )


def anchored_initial_score(penalty: float) -> float:
    initial = credibility.INITIAL_SCORE
    capped = min(max(0.0, penalty), _penalty_max())
    return max(0.0, initial - capped)


def get_owner_penalty(conn: sqlite3.Connection, owner_id: str | None) -> float:
    if not owner_id:
        return 0.0
    ensure_owner_anchoring_schema(conn)
    row = conn.execute(
        "SELECT penalty_score FROM owners WHERE owner_id = ?",
        (owner_id,),
    ).fetchone()
    if row is None:
        return 0.0
    return float(row["penalty_score"] or 0.0)


def add_owner_penalty(
    conn: sqlite3.Connection,
    owner_id: str,
    delta: float,
) -> float:
    if delta <= 0:
        return get_owner_penalty(conn, owner_id)
    ensure_owner_anchoring_schema(conn)
    current = get_owner_penalty(conn, owner_id)
    new_score = min(_penalty_max(), current + delta)
    conn.execute(
        """
        UPDATE owners
        SET penalty_score = ?
        WHERE owner_id = ?
        """,
        (new_score, owner_id),
    )
    return new_score


def owner_anchoring_summary(
    conn: sqlite3.Connection,
    owner_id: str,
) -> dict[str, float | str] | None:
    ensure_owner_anchoring_schema(conn)
    row = conn.execute(
        "SELECT owner_id, github_login, penalty_score FROM owners WHERE owner_id = ?",
        (owner_id,),
    ).fetchone()
    if row is None:
        return None
    penalty = float(row["penalty_score"] or 0.0)
    return {
        "owner_id": str(row["owner_id"]),
        "github_login": str(row["github_login"]),
        "penalty_score": penalty,
        "anchored_initial_score": anchored_initial_score(penalty),
    }


def apply_owner_penalty_for_agent(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    delta: float,
) -> float | None:
    row = conn.execute(
        "SELECT owner_id FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if row is None or not row["owner_id"]:
        return None
    return add_owner_penalty(conn, str(row["owner_id"]), delta)


def apply_quarantine_owner_penalty(conn: sqlite3.Connection, *, agent_id: str) -> float | None:
    return apply_owner_penalty_for_agent(
        conn, agent_id=agent_id, delta=QUARANTINE_PENALTY
    )


def apply_canary_failure_owner_penalty(conn: sqlite3.Connection, *, agent_id: str) -> float | None:
    return apply_owner_penalty_for_agent(conn, agent_id=agent_id, delta=CANARY_PENALTY)


def apply_flag_high_owner_penalty(conn: sqlite3.Connection, *, agent_id: str) -> float | None:
    return apply_owner_penalty_for_agent(conn, agent_id=agent_id, delta=FLAG_HIGH_PENALTY)
