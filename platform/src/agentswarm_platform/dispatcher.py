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


def select_agent_for_need(
    conn: sqlite3.Connection,
    *,
    capability_required: str,
    constraints: dict[str, Any],
) -> dict[str, Any] | None:
    exclude_owners = _exclude_owners_from_constraints(constraints)
    exclude_agents = _exclude_agent_ids_from_constraints(constraints)
    candidates = list_idle_agents_for_capability(
        conn, capability_required, exclude_owners=exclude_owners
    )
    if not candidates and exclude_owners:
        candidates = list_idle_agents_for_capability(
            conn, capability_required, exclude_owners=set()
        )
    if exclude_agents:
        candidates = [c for c in candidates if c["agent_id"] not in exclude_agents]
    if capability_required == "reviewer":
        candidates = [
            candidate
            for candidate in candidates
            if agent_meets_reviewer_hardware(
                model_id=candidate.get("model_id"),
                vram_gb=candidate.get("vram_gb"),
            )
        ]
    if not candidates:
        return None
    top_load = candidates[0]["load"]
    tier = [c for c in candidates if c["load"] <= top_load + 0.05]
    return random.choice(tier)


def dispatch_pool_need(conn: sqlite3.Connection, need_row: sqlite3.Row) -> str | None:
    constraints = json.loads(need_row["constraints_json"])
    selected = select_agent_for_need(
        conn,
        capability_required=need_row["capability_required"],
        constraints=constraints,
    )
    if selected is None:
        return None
    return selected["agent_id"]
