from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from agentswarm_platform.canary import canary_passes, parse_canary_expectation
from agentswarm_platform.credibility import credibility_enabled
from agentswarm_platform.models import utc_now_iso


def ensure_canary_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS canary_events (
            event_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            passed INTEGER NOT NULL,
            expected TEXT NOT NULL,
            actual TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


def record_canary_result(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    task_id: str,
    task_type: str,
    expected: dict[str, Any],
    result: dict[str, Any],
    passed: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO canary_events (
            event_id, agent_id, task_id, task_type, passed, expected, actual, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"canary_{uuid.uuid4().hex[:12]}",
            agent_id,
            task_id,
            task_type,
            1 if passed else 0,
            json.dumps(expected),
            json.dumps(result),
            utc_now_iso(),
        ),
    )


def get_canary_stats(conn: sqlite3.Connection, agent_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS attempts,
            COALESCE(SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END), 0) AS failures
        FROM canary_events
        WHERE agent_id = ?
        """,
        (agent_id,),
    ).fetchone()
    attempts = int(row["attempts"])
    failures = int(row["failures"])
    rate = (failures / attempts) if attempts else 0.0
    return {
        "agent_id": agent_id,
        "attempts": attempts,
        "failures": failures,
        "failure_rate": round(rate, 4),
    }


def evaluate_canary(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    task_id: str,
    task_type: str,
    task_payload: dict[str, Any],
    shared_payload: dict[str, Any] | None,
    result: dict[str, Any],
    capability: str,
) -> bool | None:
    expected = parse_canary_expectation(task_payload)
    if expected is None and shared_payload is not None:
        expected = parse_canary_expectation(shared_payload)
    if expected is None:
        return None
    passed = canary_passes(task_type, expected, result)
    record_canary_result(
        conn,
        agent_id=agent_id,
        task_id=task_id,
        task_type=task_type,
        expected=expected,
        result=result,
        passed=passed,
    )
    if not passed and credibility_enabled():
        from agentswarm_platform.credibility_ledger import _apply_delta

        _apply_delta(
            conn,
            agent_id=agent_id,
            capability=capability,
            delta=-2.0,
            reason="burn.canary",
            ref_type="task",
            ref_id=task_id,
            details={"expected": expected, "actual": result},
        )
    return passed
