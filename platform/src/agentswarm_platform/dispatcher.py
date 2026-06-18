from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from agentswarm_platform.hardware_gates import agent_meets_reviewer_hardware
from agentswarm_platform.presence_store import list_idle_agents_for_capability


def _exclude_owners_from_constraints(constraints: dict[str, Any]) -> set[str]:
    raw = constraints.get("exclude_owners") or constraints.get("exclude_owner_ids") or []
    return {str(item) for item in raw}


def _exclude_agent_ids_from_constraints(constraints: dict[str, Any]) -> set[str]:
    raw = constraints.get("exclude_agent_ids") or constraints.get("exclude_agents") or []
    return {str(item) for item in raw}


def _include_owners_from_constraints(constraints: dict[str, Any]) -> set[str]:
    raw = constraints.get("include_owners") or []
    return {str(item) for item in raw}


def select_agent_for_need(
    conn: sqlite3.Connection,
    *,
    capability_required: str,
    constraints: dict[str, Any],
    replication_group_id: str | None = None,
) -> dict[str, Any] | None:
    exclude_owners = _exclude_owners_from_constraints(constraints)
    exclude_agents = _exclude_agent_ids_from_constraints(constraints)
    include_owners = _include_owners_from_constraints(constraints)
    candidates = list_idle_agents_for_capability(
        conn, capability_required, exclude_owners=exclude_owners
    )
    if not include_owners and not candidates and exclude_owners:
        candidates = list_idle_agents_for_capability(
            conn, capability_required, exclude_owners=set()
        )
    if exclude_agents:
        candidates = [c for c in candidates if c["agent_id"] not in exclude_agents]
    if include_owners:
        candidates = [c for c in candidates if c["owner"] in include_owners]
    if capability_required == "reviewer":
        candidates = [
            candidate
            for candidate in candidates
            if agent_meets_reviewer_hardware(
                model_id=candidate.get("model_id"),
                vram_gb=candidate.get("vram_gb"),
                constraints=constraints,
            )
        ]
    if replication_group_id:
        in_group = {
            str(row["claimed_by"])
            for row in conn.execute(
                """
                SELECT DISTINCT claimed_by FROM tasks
                WHERE replication_group_id = ? AND claimed_by IS NOT NULL
                """,
                (replication_group_id,),
            ).fetchall()
        }
        candidates = [c for c in candidates if c["agent_id"] not in in_group]
    if not candidates:
        return None
    top_load = candidates[0]["load"]
    tier = [c for c in candidates if c["load"] <= top_load + 0.05]
    return random.choice(tier)


def dispatch_pool_need(
    conn: sqlite3.Connection,
    need_row: sqlite3.Row,
    *,
    preferred_agent_id: str | None = None,
) -> str | None:
    from agentswarm_platform.dispatch_store import agent_matches_pool_need

    constraints = json.loads(need_row["constraints_json"])
    replication_group_id: str | None = None
    task_id = need_row["task_id"]
    if task_id:
        task_row = conn.execute(
            "SELECT replication_group_id FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if task_row is not None and task_row["replication_group_id"]:
            replication_group_id = str(task_row["replication_group_id"])
    if preferred_agent_id and agent_matches_pool_need(
        conn,
        preferred_agent_id,
        need_row,
        replication_group_id=replication_group_id,
    ):
        return preferred_agent_id
    selected = select_agent_for_need(
        conn,
        capability_required=need_row["capability_required"],
        constraints=constraints,
        replication_group_id=replication_group_id,
    )
    if selected is None:
        return None
    return selected["agent_id"]
