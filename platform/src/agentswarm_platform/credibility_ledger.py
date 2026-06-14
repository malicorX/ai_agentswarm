from __future__ import annotations

import json
import sqlite3
from typing import Any

from agentswarm_platform.credibility import (
    INITIAL_SCORE,
    compute_outcome_deltas,
    credibility_enabled,
    new_ledger_entry_id,
    stake_amount,
    task_stake_tier,
)
from agentswarm_platform.models import utc_now_iso
from agentswarm_platform.project_store import DEFAULT_PROJECT_ID


def project_id_from_task_row(row: sqlite3.Row) -> str:
    keys = row.keys()
    if "project_id" in keys and row["project_id"]:
        return row["project_id"]
    return DEFAULT_PROJECT_ID


def ensure_credibility_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS credibility_balances (
            agent_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            score REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (agent_id, capability)
        );

        CREATE TABLE IF NOT EXISTS credibility_ledger (
            entry_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            delta REAL NOT NULL,
            balance_after REAL NOT NULL,
            reason TEXT NOT NULL,
            ref_type TEXT,
            ref_id TEXT,
            details TEXT NOT NULL
        );
        """
    )
    balance_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(credibility_balances)").fetchall()
    }
    if "project_id" not in balance_columns:
        conn.executescript(
            f"""
            CREATE TABLE credibility_balances_v2 (
                agent_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                project_id TEXT NOT NULL,
                score REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (agent_id, capability, project_id)
            );

            INSERT INTO credibility_balances_v2 (
                agent_id, capability, project_id, score, updated_at
            )
            SELECT agent_id, capability, '{DEFAULT_PROJECT_ID}', score, updated_at
            FROM credibility_balances;

            DROP TABLE credibility_balances;
            ALTER TABLE credibility_balances_v2 RENAME TO credibility_balances;
            """
        )
    ledger_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(credibility_ledger)").fetchall()
    }
    if "project_id" not in ledger_columns:
        conn.execute(
            f"ALTER TABLE credibility_ledger ADD COLUMN project_id TEXT NOT NULL DEFAULT '{DEFAULT_PROJECT_ID}'"
        )
    task_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    if "stake_amount" not in task_columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN stake_amount REAL")


def seed_agent_capabilities(
    conn: sqlite3.Connection,
    agent_id: str,
    capabilities: list[str],
    project_id: str = DEFAULT_PROJECT_ID,
) -> None:
    if not credibility_enabled():
        return
    for capability in capabilities:
        existing = conn.execute(
            """
            SELECT 1 FROM credibility_balances
            WHERE agent_id = ? AND capability = ? AND project_id = ?
            """,
            (agent_id, capability, project_id),
        ).fetchone()
        if existing is not None:
            continue
        _apply_delta(
            conn,
            agent_id=agent_id,
            capability=capability,
            project_id=project_id,
            delta=INITIAL_SCORE,
            reason="seed.initial",
            ref_type="agent",
            ref_id=agent_id,
            details={"initial_score": INITIAL_SCORE, "project_id": project_id},
        )


def get_balance(
    conn: sqlite3.Connection,
    agent_id: str,
    capability: str,
    project_id: str = DEFAULT_PROJECT_ID,
) -> float:
    row = conn.execute(
        """
        SELECT score FROM credibility_balances
        WHERE agent_id = ? AND capability = ? AND project_id = ?
        """,
        (agent_id, capability, project_id),
    ).fetchone()
    if row is None:
        return 0.0
    return float(row["score"])


def list_agent_credibility(
    conn: sqlite3.Connection,
    agent_id: str,
    project_id: str = DEFAULT_PROJECT_ID,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT capability, score, updated_at, project_id
        FROM credibility_balances
        WHERE agent_id = ? AND project_id = ?
        ORDER BY capability ASC
        """,
        (agent_id, project_id),
    ).fetchall()
    return [
        {
            "capability": row["capability"],
            "score": float(row["score"]),
            "updated_at": row["updated_at"],
            "project_id": row["project_id"],
        }
        for row in rows
    ]


def leaderboard(
    conn: sqlite3.Connection,
    capability: str | None,
    limit: int,
    project_id: str = DEFAULT_PROJECT_ID,
) -> list[dict[str, Any]]:
    if capability:
        rows = conn.execute(
            """
            SELECT b.agent_id, b.capability, b.score, b.updated_at, b.project_id, a.owner
            FROM credibility_balances b
            JOIN agents a ON a.agent_id = b.agent_id
            WHERE b.capability = ? AND b.project_id = ?
            ORDER BY b.score DESC
            LIMIT ?
            """,
            (capability, project_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT b.agent_id, b.capability, b.score, b.updated_at, b.project_id, a.owner
            FROM credibility_balances b
            JOIN agents a ON a.agent_id = b.agent_id
            WHERE b.project_id = ?
            ORDER BY b.score DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return [
        {
            "agent_id": row["agent_id"],
            "owner": row["owner"],
            "capability": row["capability"],
            "score": float(row["score"]),
            "updated_at": row["updated_at"],
            "project_id": row["project_id"],
        }
        for row in rows
    ]


def lock_claim_stake(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    capability: str,
    task_id: str,
    project_id: str = DEFAULT_PROJECT_ID,
) -> float:
    if not credibility_enabled():
        return 0.0
    score = get_balance(conn, agent_id, capability, project_id)
    stake = stake_amount(score)
    if stake <= 0:
        return 0.0
    _apply_delta(
        conn,
        agent_id=agent_id,
        capability=capability,
        project_id=project_id,
        delta=-stake,
        reason="stake.lock",
        ref_type="task",
        ref_id=task_id,
        details={"stake": stake, "project_id": project_id},
    )
    conn.execute(
        "UPDATE tasks SET stake_amount = ? WHERE task_id = ?",
        (stake, task_id),
    )
    return stake


def apply_task_outcome(
    conn: sqlite3.Connection,
    *,
    parent_task_row: sqlite3.Row,
    verdict: str,
    reviewer_agent_id: str,
) -> None:
    if not credibility_enabled():
        return
    project_id = project_id_from_task_row(parent_task_row)
    accepted = verdict == "approve"
    payload = json.loads(parent_task_row["payload"])
    tier = task_stake_tier(payload)
    submitter_id = parent_task_row["claimed_by"]
    submitter_cap = parent_task_row["capability_required"]
    stake = float(parent_task_row["stake_amount"] or 0.0)
    verifier_score = get_balance(conn, reviewer_agent_id, "reviewer", project_id)
    deltas = compute_outcome_deltas(
        accepted=accepted,
        submitter_capability=submitter_cap,
        task_tier=tier,
        stake=stake,
        verifier_score=verifier_score,
    )

    if accepted and stake > 0:
        _apply_delta(
            conn,
            agent_id=submitter_id,
            capability=submitter_cap,
            project_id=project_id,
            delta=stake,
            reason="stake.return",
            ref_type="task",
            ref_id=parent_task_row["task_id"],
            details={"stake": stake, "project_id": project_id},
        )
    if accepted:
        _apply_delta(
            conn,
            agent_id=submitter_id,
            capability=submitter_cap,
            project_id=project_id,
            delta=deltas.mint,
            reason="mint.accept",
            ref_type="task",
            ref_id=parent_task_row["task_id"],
            details={
                "tier": tier,
                "verifier_score": verifier_score,
                "mint": deltas.mint,
                "project_id": project_id,
            },
        )
    elif not accepted:
        _apply_delta(
            conn,
            agent_id=submitter_id,
            capability=submitter_cap,
            project_id=project_id,
            delta=-deltas.burn,
            reason="burn.reject",
            ref_type="task",
            ref_id=parent_task_row["task_id"],
            details={"tier": tier, "burn": deltas.burn, "project_id": project_id},
        )

    _apply_delta(
        conn,
        agent_id=reviewer_agent_id,
        capability="reviewer",
        project_id=project_id,
        delta=deltas.reviewer_delta,
        reason="mint.verify",
        ref_type="task",
        ref_id=parent_task_row["task_id"],
        details={"verdict": verdict, "project_id": project_id},
    )


def _apply_delta(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    capability: str,
    project_id: str,
    delta: float,
    reason: str,
    ref_type: str | None,
    ref_id: str | None,
    details: dict[str, Any],
) -> float:
    current = get_balance(conn, agent_id, capability, project_id)
    new_score = max(0.0, current + delta)
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO credibility_balances (
            agent_id, capability, project_id, score, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(agent_id, capability, project_id) DO UPDATE SET
            score = excluded.score,
            updated_at = excluded.updated_at
        """,
        (agent_id, capability, project_id, new_score, now),
    )
    conn.execute(
        """
        INSERT INTO credibility_ledger (
            entry_id, timestamp, agent_id, capability, project_id, delta, balance_after,
            reason, ref_type, ref_id, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_ledger_entry_id(),
            now,
            agent_id,
            capability,
            project_id,
            delta,
            new_score,
            reason,
            ref_type,
            ref_id,
            json.dumps(details),
        ),
    )
    return new_score
