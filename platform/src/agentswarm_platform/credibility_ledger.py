from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from agentswarm_platform.bounty import parse_bounty_bonus
from agentswarm_platform.credibility import (
    INITIAL_SCORE,
    PARALLEL_VERIFIER_SCORE,
    agent_meets_stake_tier,
    compute_outcome_deltas,
    credibility_enabled,
    decay_score,
    DECAY_MIN_DAYS,
    min_credibility_for_tier,
    new_ledger_entry_id,
    stake_amount,
    stake_tier_label,
    task_stake_tier,
)
from agentswarm_platform.credibility_gamification import enrich_leaderboard_entry
from agentswarm_platform.models import utc_now_iso
from agentswarm_platform.credibility_transfer import (
    CROSS_PROJECT_HAIRCUT,
    compute_imported_score,
)
from agentswarm_platform.owner_anchoring import (
    anchored_initial_score,
    get_owner_penalty,
)
from agentswarm_platform.project_store import (
    DEFAULT_PROJECT_ID,
    agent_project_ids,
    get_project,
    validate_project_id,
)


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
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS credibility_imports (
            import_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            source_project_id TEXT NOT NULL,
            target_project_id TEXT NOT NULL,
            source_score REAL NOT NULL,
            imported_score REAL NOT NULL,
            haircut_rate REAL NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, capability, source_project_id, target_project_id)
        );
        """
    )


def seed_agent_capabilities(
    conn: sqlite3.Connection,
    agent_id: str,
    capabilities: list[str],
    project_id: str = DEFAULT_PROJECT_ID,
) -> None:
    if not credibility_enabled():
        return
    owner_row = conn.execute(
        "SELECT owner_id FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    owner_id = str(owner_row["owner_id"]) if owner_row and owner_row["owner_id"] else None
    penalty = get_owner_penalty(conn, owner_id)
    initial_score = anchored_initial_score(penalty)
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
            delta=initial_score,
            reason="seed.initial",
            ref_type="agent",
            ref_id=agent_id,
            details={
                "initial_score": initial_score,
                "project_id": project_id,
                "owner_penalty": penalty,
            },
            apply_decay_before=False,
        )


def _parse_updated_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _raw_balance(
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


def maybe_apply_inactivity_decay(
    conn: sqlite3.Connection,
    agent_id: str,
    capability: str,
    project_id: str = DEFAULT_PROJECT_ID,
) -> bool:
    if not credibility_enabled():
        return False
    row = conn.execute(
        """
        SELECT score, updated_at FROM credibility_balances
        WHERE agent_id = ? AND capability = ? AND project_id = ?
        """,
        (agent_id, capability, project_id),
    ).fetchone()
    if row is None:
        return False
    score = float(row["score"])
    updated_at = _parse_updated_at(str(row["updated_at"]))
    now = datetime.now(timezone.utc)
    days_inactive = (now - updated_at).total_seconds() / 86400.0
    if days_inactive < DECAY_MIN_DAYS:
        return False
    new_score = max(0.0, decay_score(score, days_inactive))
    delta = new_score - score
    if abs(delta) < 0.001:
        return False
    _apply_delta(
        conn,
        agent_id=agent_id,
        capability=capability,
        project_id=project_id,
        delta=delta,
        reason="decay.inactivity",
        ref_type="decay",
        ref_id=None,
        details={"days_inactive": days_inactive, "project_id": project_id},
        apply_decay_before=False,
    )
    return True


def get_balance(
    conn: sqlite3.Connection,
    agent_id: str,
    capability: str,
    project_id: str = DEFAULT_PROJECT_ID,
) -> float:
    maybe_apply_inactivity_decay(conn, agent_id, capability, project_id)
    return _raw_balance(conn, agent_id, capability, project_id)


def apply_inactivity_decay_all(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
) -> dict[str, int]:
    if project_id is None:
        rows = conn.execute(
            "SELECT agent_id, capability, project_id FROM credibility_balances"
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT agent_id, capability, project_id
            FROM credibility_balances
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchall()
    updated = 0
    for row in rows:
        if maybe_apply_inactivity_decay(
            conn,
            str(row["agent_id"]),
            str(row["capability"]),
            str(row["project_id"]),
        ):
            updated += 1
    return {"checked": len(rows), "updated": updated}


def agent_can_claim_by_tier(
    conn: sqlite3.Connection,
    agent_id: str,
    capability: str,
    project_id: str,
    payload: dict[str, Any],
) -> bool:
    if not credibility_enabled():
        return True
    score = get_balance(conn, agent_id, capability, project_id)
    return agent_meets_stake_tier(score, payload)


def assert_claim_tier_allowed(
    conn: sqlite3.Connection,
    agent_id: str,
    capability: str,
    project_id: str,
    payload: dict[str, Any],
) -> None:
    if not credibility_enabled():
        return
    tier = task_stake_tier(payload)
    if tier == 1:
        return
    score = get_balance(conn, agent_id, capability, project_id)
    required = min_credibility_for_tier(tier)
    if score < required:
        label = stake_tier_label(tier)
        raise ValueError(
            f"credibility floor not met for stake_tier={label} "
            f"(need {required}, have {score})"
        )


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
    result: list[dict[str, Any]] = []
    for row in rows:
        capability = str(row["capability"])
        maybe_apply_inactivity_decay(conn, agent_id, capability, project_id)
        balance_row = conn.execute(
            """
            SELECT score, updated_at FROM credibility_balances
            WHERE agent_id = ? AND capability = ? AND project_id = ?
            """,
            (agent_id, capability, project_id),
        ).fetchone()
        assert balance_row is not None
        result.append(
            {
                "capability": capability,
                "score": float(balance_row["score"]),
                "updated_at": balance_row["updated_at"],
                "project_id": row["project_id"],
            }
        )
    return result


def leaderboard(
    conn: sqlite3.Connection,
    capability: str | None,
    limit: int,
    project_id: str = DEFAULT_PROJECT_ID,
) -> list[dict[str, Any]]:
    if capability:
        balance_rows = conn.execute(
            """
            SELECT agent_id, capability FROM credibility_balances
            WHERE capability = ? AND project_id = ?
            """,
            (capability, project_id),
        ).fetchall()
    else:
        balance_rows = conn.execute(
            """
            SELECT agent_id, capability FROM credibility_balances
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchall()
    for row in balance_rows:
        maybe_apply_inactivity_decay(
            conn,
            str(row["agent_id"]),
            str(row["capability"]),
            project_id,
        )

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
        enrich_leaderboard_entry(
            conn,
            {
                "agent_id": row["agent_id"],
                "owner": row["owner"],
                "capability": row["capability"],
                "score": float(row["score"]),
                "updated_at": row["updated_at"],
                "project_id": row["project_id"],
            },
            project_id,
        )
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
    reviewer_agent_id: str | None,
    award_reviewer: bool = True,
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
    if reviewer_agent_id:
        verifier_score = get_balance(conn, reviewer_agent_id, "reviewer", project_id)
    else:
        verifier_score = PARALLEL_VERIFIER_SCORE
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
        bounty_bonus = parse_bounty_bonus(payload)
        if bounty_bonus > 0:
            _apply_delta(
                conn,
                agent_id=submitter_id,
                capability=submitter_cap,
                project_id=project_id,
                delta=bounty_bonus,
                reason="mint.bounty",
                ref_type="task",
                ref_id=parent_task_row["task_id"],
                details={"bonus": bounty_bonus, "project_id": project_id},
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

    if award_reviewer and reviewer_agent_id:
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


def apply_good_attempt_reward(
    conn: sqlite3.Connection,
    *,
    task_row: sqlite3.Row,
    amount: float,
) -> None:
    if not credibility_enabled() or amount <= 0:
        return
    project_id = project_id_from_task_row(task_row)
    submitter_id = task_row["claimed_by"]
    capability = task_row["capability_required"]
    stake = float(task_row["stake_amount"] or 0.0)
    if stake > 0:
        _apply_delta(
            conn,
            agent_id=submitter_id,
            capability=capability,
            project_id=project_id,
            delta=stake,
            reason="stake.return",
            ref_type="task",
            ref_id=task_row["task_id"],
            details={"stake": stake, "project_id": project_id},
        )
    _apply_delta(
        conn,
        agent_id=submitter_id,
        capability=capability,
        project_id=project_id,
        delta=amount,
        reason="mint.good_attempt",
        ref_type="task",
        ref_id=task_row["task_id"],
        details={"amount": amount, "project_id": project_id},
    )


def apply_parallel_winner_outcome(
    conn: sqlite3.Connection,
    *,
    task_row: sqlite3.Row,
    verifier_score: float = PARALLEL_VERIFIER_SCORE,
) -> None:
    if not credibility_enabled():
        return
    project_id = project_id_from_task_row(task_row)
    payload = json.loads(task_row["payload"])
    tier = task_stake_tier(payload)
    submitter_id = task_row["claimed_by"]
    submitter_cap = task_row["capability_required"]
    stake = float(task_row["stake_amount"] or 0.0)
    deltas = compute_outcome_deltas(
        accepted=True,
        submitter_capability=submitter_cap,
        task_tier=tier,
        stake=stake,
        verifier_score=verifier_score,
    )
    if stake > 0:
        _apply_delta(
            conn,
            agent_id=submitter_id,
            capability=submitter_cap,
            project_id=project_id,
            delta=stake,
            reason="stake.return",
            ref_type="task",
            ref_id=task_row["task_id"],
            details={"stake": stake, "project_id": project_id},
        )
    _apply_delta(
        conn,
        agent_id=submitter_id,
        capability=submitter_cap,
        project_id=project_id,
        delta=deltas.mint,
        reason="mint.accept",
        ref_type="task",
        ref_id=task_row["task_id"],
        details={
            "tier": tier,
            "verifier_score": verifier_score,
            "mint": deltas.mint,
            "project_id": project_id,
            "parallel": True,
        },
    )
    bounty_bonus = parse_bounty_bonus(payload)
    if bounty_bonus > 0:
        _apply_delta(
            conn,
            agent_id=submitter_id,
            capability=submitter_cap,
            project_id=project_id,
            delta=bounty_bonus,
            reason="mint.bounty",
            ref_type="task",
            ref_id=task_row["task_id"],
            details={"bonus": bounty_bonus, "project_id": project_id},
        )


def apply_parallel_group_credibility(
    conn: sqlite3.Connection,
    *,
    group_id: str,
    task_type: str,
    winning_fingerprint: str | None,
    disputed: bool,
    good_attempt_mint: float,
) -> None:
    if not credibility_enabled():
        return
    tasks = conn.execute(
        """
        SELECT * FROM tasks
        WHERE replication_group_id = ? AND submission_result IS NOT NULL
        """,
        (group_id,),
    ).fetchall()
    from agentswarm_platform.models import TaskStatus
    from agentswarm_platform.replication import result_fingerprint

    for task in tasks:
        if task["status"] not in (
            TaskStatus.VERIFIED.value,
            TaskStatus.REJECTED.value,
        ):
            continue
        result = json.loads(task["submission_result"])
        fp = result_fingerprint(task_type, result)
        if disputed:
            if good_attempt_mint > 0:
                apply_good_attempt_reward(conn, task_row=task, amount=good_attempt_mint)
            continue
        if winning_fingerprint and fp == winning_fingerprint:
            apply_parallel_winner_outcome(conn, task_row=task)
        elif good_attempt_mint > 0:
            apply_good_attempt_reward(conn, task_row=task, amount=good_attempt_mint)


def apply_major_version_haircut(conn: sqlite3.Connection, agent_id: str) -> int:
    """Haircut earned credibility after a major version bump (ROADMAP §14)."""
    if not credibility_enabled():
        return 0
    haircut = float(os.environ.get("AGENTSWARM_VERSION_MAJOR_HAIRCUT", "0.5"))
    rows = conn.execute(
        """
        SELECT capability, project_id, score
        FROM credibility_balances
        WHERE agent_id = ?
        """,
        (agent_id,),
    ).fetchall()
    adjusted = 0
    for row in rows:
        old_score = float(row["score"])
        new_score = compute_imported_score(
            old_score,
            haircut=haircut,
            initial_score=INITIAL_SCORE,
        )
        delta = new_score - old_score
        if abs(delta) < 1e-9:
            continue
        _apply_delta(
            conn,
            agent_id=agent_id,
            capability=str(row["capability"]),
            project_id=str(row["project_id"]),
            delta=delta,
            reason="version.major_haircut",
            ref_type="agent",
            ref_id=agent_id,
            details={
                "haircut": haircut,
                "previous_score": old_score,
                "new_score": new_score,
            },
        )
        adjusted += 1
    return adjusted


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
    apply_decay_before: bool = True,
) -> float:
    if apply_decay_before:
        maybe_apply_inactivity_decay(conn, agent_id, capability, project_id)
    current = _raw_balance(conn, agent_id, capability, project_id)
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


def import_cross_project_credibility(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    source_project_id: str,
    target_project_id: str,
    capabilities: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not credibility_enabled():
        raise ValueError("credibility is disabled")
    source = validate_project_id(source_project_id)
    target = validate_project_id(target_project_id)
    if source == target:
        raise ValueError("source and target project must differ")
    if get_project(conn, source) is None:
        raise ValueError(f"unknown source project: {source}")
    if get_project(conn, target) is None:
        raise ValueError(f"unknown target project: {target}")

    memberships = agent_project_ids(conn, agent_id)
    if target not in memberships:
        raise ValueError(f"agent is not a member of target project: {target}")

    if capabilities is None:
        rows = conn.execute(
            """
            SELECT capability, score FROM credibility_balances
            WHERE agent_id = ? AND project_id = ?
            ORDER BY capability ASC
            """,
            (agent_id, source),
        ).fetchall()
        capability_scores = [(row["capability"], float(row["score"])) for row in rows]
    else:
        capability_scores = []
        for capability in capabilities:
            capability_scores.append(
                (capability, get_balance(conn, agent_id, capability, source))
            )

    if not capability_scores:
        raise ValueError("no capabilities to import")

    imported_entries: list[dict[str, Any]] = []
    now = utc_now_iso()
    for capability, source_score in capability_scores:
        if source_score <= 0:
            continue
        duplicate = conn.execute(
            """
            SELECT 1 FROM credibility_imports
            WHERE agent_id = ? AND capability = ?
              AND source_project_id = ? AND target_project_id = ?
            """,
            (agent_id, capability, source, target),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(
                f"credibility already imported for {capability} "
                f"from {source} to {target}"
            )

        imported_score = compute_imported_score(source_score)
        target_current = get_balance(conn, agent_id, capability, target)
        delta = imported_score - target_current
        if abs(delta) < 1e-9:
            continue

        balance_after = _apply_delta(
            conn,
            agent_id=agent_id,
            capability=capability,
            project_id=target,
            delta=delta,
            reason="import.cross_project",
            ref_type="project",
            ref_id=source,
            details={
                "source_project_id": source,
                "target_project_id": target,
                "source_score": source_score,
                "imported_score": imported_score,
                "haircut_rate": CROSS_PROJECT_HAIRCUT,
            },
        )
        import_id = f"import_{new_ledger_entry_id().removeprefix('cred_')}"
        conn.execute(
            """
            INSERT INTO credibility_imports (
                import_id, agent_id, capability, source_project_id, target_project_id,
                source_score, imported_score, haircut_rate, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_id,
                agent_id,
                capability,
                source,
                target,
                source_score,
                imported_score,
                CROSS_PROJECT_HAIRCUT,
                now,
            ),
        )
        imported_entries.append(
            {
                "capability": capability,
                "source_project_id": source,
                "target_project_id": target,
                "source_score": source_score,
                "imported_score": imported_score,
                "balance_after": balance_after,
                "haircut_rate": CROSS_PROJECT_HAIRCUT,
            }
        )

    if not imported_entries:
        raise ValueError("no credibility available to import for requested capabilities")
    return imported_entries
