from __future__ import annotations

import json
import os
import sqlite3
import uuid
from typing import Any

from agentswarm_platform.models import utc_now_iso


def credits_enabled() -> bool:
    return os.environ.get("AGENTSWARM_CREDITS_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    ) or os.environ.get("AGENTSWARM_ASSIGNMENT_MODE", "").lower() == "dispatch"


def initial_credits() -> float:
    return float(os.environ.get("AGENTSWARM_CREDITS_INITIAL", "100"))


def goal_post_cost() -> float:
    return float(os.environ.get("AGENTSWARM_CREDITS_GOAL_COST", "50"))


def reviewer_reward() -> float:
    return float(os.environ.get("AGENTSWARM_CREDITS_REVIEWER_REWARD", "15"))


def ensure_credits_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS credits_balances (
            agent_id TEXT PRIMARY KEY,
            balance REAL NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS credits_ledger (
            entry_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            delta REAL NOT NULL,
            balance_after REAL NOT NULL,
            reason TEXT NOT NULL,
            ref_type TEXT,
            ref_id TEXT,
            details TEXT NOT NULL DEFAULT '{}'
        );
        """
    )


def get_credits_balance(conn: sqlite3.Connection, agent_id: str) -> float:
    row = conn.execute(
        "SELECT balance FROM credits_balances WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    if row is not None:
        return float(row["balance"])
    if not credits_enabled():
        return 0.0
    seed = initial_credits()
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO credits_balances (agent_id, balance, updated_at)
        VALUES (?, ?, ?)
        """,
        (agent_id, seed, now),
    )
    conn.execute(
        """
        INSERT INTO credits_ledger (
            entry_id, timestamp, agent_id, delta, balance_after,
            reason, ref_type, ref_id, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"cred-{uuid.uuid4().hex[:12]}",
            now,
            agent_id,
            seed,
            seed,
            "initial_grant",
            "agent",
            agent_id,
            json.dumps({}),
        ),
    )
    return seed


def _apply_credits_delta(
    conn: sqlite3.Connection,
    agent_id: str,
    delta: float,
    *,
    reason: str,
    ref_type: str | None,
    ref_id: str | None,
    details: dict[str, Any] | None = None,
) -> float:
    balance = get_credits_balance(conn, agent_id)
    new_balance = balance + delta
    if new_balance < -1e-9:
        raise ValueError(f"insufficient credits: have {balance}, need {-delta}")
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE credits_balances SET balance = ?, updated_at = ? WHERE agent_id = ?
        """,
        (new_balance, now, agent_id),
    )
    conn.execute(
        """
        INSERT INTO credits_ledger (
            entry_id, timestamp, agent_id, delta, balance_after,
            reason, ref_type, ref_id, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"cred-{uuid.uuid4().hex[:12]}",
            now,
            agent_id,
            delta,
            new_balance,
            reason,
            ref_type,
            ref_id,
            json.dumps(details or {}),
        ),
    )
    return new_balance


def burn_credits(
    conn: sqlite3.Connection,
    agent_id: str,
    amount: float,
    *,
    reason: str,
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> float:
    if amount <= 0:
        raise ValueError("burn amount must be positive")
    return _apply_credits_delta(
        conn,
        agent_id,
        -amount,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
    )


def mint_credits(
    conn: sqlite3.Connection,
    agent_id: str,
    amount: float,
    *,
    reason: str,
    ref_type: str | None = None,
    ref_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> float:
    if amount <= 0:
        raise ValueError("mint amount must be positive")
    return _apply_credits_delta(
        conn,
        agent_id,
        amount,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
        details=details,
    )
