from __future__ import annotations

import os
import sqlite3
from typing import Any

from agentswarm_platform.credibility import credibility_enabled
from agentswarm_platform.credibility_ledger import get_balance
from agentswarm_platform.project_store import (
    DEFAULT_PROJECT_ID,
    agent_project_ids,
    validate_project_id,
)

DEFAULT_MEMORY_WRITE_SUFFIX = "news-backlog"
MEMORY_WRITE_MIN_SCORE = float(
    os.environ.get("AGENTSWARM_MEMORY_WRITE_MIN_SCORE", "25")
)


def memory_write_capabilities() -> set[str]:
    raw = os.environ.get(
        "AGENTSWARM_MEMORY_WRITE_CAPABILITIES",
        "orchestrator,planner",
    )
    return {part.strip() for part in raw.split(",") if part.strip()}


def project_id_for_memory_key(memory_key: str) -> str:
    if memory_key == DEFAULT_MEMORY_WRITE_SUFFIX:
        return DEFAULT_PROJECT_ID
    if "." not in memory_key:
        return DEFAULT_PROJECT_ID
    prefix, _suffix = memory_key.split(".", 1)
    try:
        return validate_project_id(prefix)
    except ValueError:
        return DEFAULT_PROJECT_ID


def assert_agent_memory_write_allowed(
    conn: sqlite3.Connection,
    *,
    agent: dict[str, Any],
    agent_id: str,
    memory_key: str,
) -> str:
    project_id = project_id_for_memory_key(memory_key)
    memberships = agent_project_ids(conn, agent_id)
    if project_id not in memberships:
        raise ValueError(f"agent is not a member of project {project_id}")

    write_caps = memory_write_capabilities()
    agent_caps = set(agent.get("capabilities") or [])
    eligible = write_caps & agent_caps
    if not eligible:
        raise ValueError(
            "agent lacks a memory-write capability "
            f"({', '.join(sorted(write_caps))})"
        )

    if credibility_enabled():
        best_score = max(
            get_balance(conn, agent_id, capability, project_id)
            for capability in eligible
        )
        if best_score < MEMORY_WRITE_MIN_SCORE:
            raise ValueError(
                "credibility floor not met for memory write "
                f"(need {MEMORY_WRITE_MIN_SCORE}, have {best_score})"
            )

    return project_id
