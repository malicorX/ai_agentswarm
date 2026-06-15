from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from typing import Any

from agentswarm_platform.credibility import (
    credibility_enabled,
    stake_tier_label,
    task_stake_tier,
)
from agentswarm_platform.models import utc_now_iso


def probation_verifications_required() -> int:
    raw = os.environ.get("AGENTSWARM_VERSION_PROBATION_VERIFICATIONS", "3").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 3
    return max(0, value)


def probation_enabled() -> bool:
    return credibility_enabled() and probation_verifications_required() > 0


def ensure_probation_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
    if "version_probation_remaining" not in columns:
        conn.execute(
            "ALTER TABLE agents ADD COLUMN version_probation_remaining INTEGER NOT NULL DEFAULT 0"
        )


def public_parameters() -> dict[str, float | int | bool]:
    required = probation_verifications_required()
    return {
        "probation_enabled": probation_enabled(),
        "probation_verifications_required": required,
        "major_haircut": float(os.environ.get("AGENTSWARM_VERSION_MAJOR_HAIRCUT", "0.5")),
    }


def get_probation_remaining(conn: sqlite3.Connection, agent_id: str) -> int:
    row = conn.execute(
        "SELECT version_probation_remaining FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    if row is None:
        return 0
    return max(0, int(row["version_probation_remaining"] or 0))


def is_on_probation(conn: sqlite3.Connection, agent_id: str) -> bool:
    return probation_enabled() and get_probation_remaining(conn, agent_id) > 0


def probation_status(conn: sqlite3.Connection, agent_id: str) -> dict[str, Any]:
    remaining = get_probation_remaining(conn, agent_id)
    required = probation_verifications_required()
    return {
        "active": probation_enabled() and remaining > 0,
        "remaining": remaining,
        "required": required,
    }


def start_major_version_probation(conn: sqlite3.Connection, agent_id: str) -> int:
    """Reset probation counter after a major version bump."""
    if not probation_enabled():
        return 0
    required = probation_verifications_required()
    conn.execute(
        "UPDATE agents SET version_probation_remaining = ? WHERE agent_id = ?",
        (required, agent_id),
    )
    return required


def assert_probation_allows_claim(
    conn: sqlite3.Connection,
    agent_id: str,
    payload: dict[str, Any],
) -> None:
    if not is_on_probation(conn, agent_id):
        return
    tier = task_stake_tier(payload)
    if tier <= 1:
        return
    remaining = get_probation_remaining(conn, agent_id)
    label = stake_tier_label(tier)
    raise ValueError(
        f"major-version probation active ({remaining} verification(s) remaining); "
        f"stake_tier={label} not allowed"
    )


def agent_can_claim_during_probation(
    conn: sqlite3.Connection,
    agent_id: str,
    payload: dict[str, Any],
) -> bool:
    if not is_on_probation(conn, agent_id):
        return True
    return task_stake_tier(payload) <= 1


def record_probation_verification(
    conn: sqlite3.Connection,
    agent_id: str,
    *,
    task_id: str,
) -> int:
    """Decrement probation after a verified accept; return remaining count."""
    if not probation_enabled():
        return 0
    remaining = get_probation_remaining(conn, agent_id)
    if remaining <= 0:
        return 0
    remaining -= 1
    conn.execute(
        "UPDATE agents SET version_probation_remaining = ? WHERE agent_id = ?",
        (remaining, agent_id),
    )
    if remaining == 0:
        _append_probation_cleared(conn, agent_id, task_id=task_id)
    return remaining


def _append_probation_cleared(
    conn: sqlite3.Connection, agent_id: str, *, task_id: str
) -> None:
    row = conn.execute(
        "SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    prev_hash = row["entry_hash"] if row else "0" * 64
    timestamp = utc_now_iso()
    details = {"task_id": task_id}
    body = json.dumps(
        {
            "timestamp": timestamp,
            "event_type": "agent.probation_cleared",
            "actor_id": agent_id,
            "details": details,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    entry_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO audit_log (timestamp, event_type, actor_id, details, prev_hash, entry_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            "agent.probation_cleared",
            agent_id,
            json.dumps(details),
            prev_hash,
            entry_hash,
        ),
    )
