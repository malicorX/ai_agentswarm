from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from agentswarm_platform.presence_store import list_idle_agents_for_capability


def _exclude_owners_from_constraints(constraints: dict[str, Any]) -> set[str]:
    raw = constraints.get("exclude_owners") or constraints.get("exclude_owner_ids") or []
    return {str(item) for item in raw}


def select_agent_for_need(
    conn: sqlite3.Connection,
    *,
    capability_required: str,
    constraints: dict[str, Any],
) -> dict[str, Any] | None:
    exclude = _exclude_owners_from_constraints(constraints)
    candidates = list_idle_agents_for_capability(
        conn, capability_required, exclude_owners=exclude
    )
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
