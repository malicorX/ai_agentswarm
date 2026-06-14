from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Callable

from agentswarm_platform.memory_store import upsert_memory_entry
from agentswarm_platform.models import TaskStatus, utc_now_iso
from agentswarm_platform.orchestration import validate_enqueue_spec


def apply_project_bootstrap(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    governance_config: dict[str, Any],
    actor_id: str | None,
    append_audit: Callable[[sqlite3.Connection, str, str | None, dict[str, Any]], None],
) -> dict[str, Any]:
    memory_seeds = governance_config.get("memory_seeds") or {}
    seeded_memory: list[str] = []
    for key, spec in memory_seeds.items():
        if not isinstance(spec, dict):
            continue
        content = spec.get("content")
        if not isinstance(content, dict):
            continue
        scoped_key = f"{project_id}.{key}"
        upsert_memory_entry(
            conn,
            memory_key=scoped_key,
            content=content,
            tags=spec.get("tags") if isinstance(spec.get("tags"), list) else [],
            updated_by=actor_id,
        )
        seeded_memory.append(scoped_key)

    bootstrap_tasks = governance_config.get("bootstrap_tasks") or []
    created_task_ids: list[str] = []
    created_at = utc_now_iso()
    for spec in bootstrap_tasks:
        if not isinstance(spec, dict):
            continue
        task_type, capability_required, payload = validate_enqueue_spec(spec)
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, capability_required, status, payload,
                parent_task_id, parent_submission_id, created_at, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                capability_required,
                TaskStatus.CREATED.value,
                json.dumps(payload),
                None,
                None,
                created_at,
                project_id,
            ),
        )
        created_task_ids.append(task_id)
        append_audit(
            conn,
            "task.created",
            actor_id,
            {
                "task_id": task_id,
                "task_type": task_type,
                "trigger": "project.bootstrap",
                "project_id": project_id,
            },
        )

    if seeded_memory or created_task_ids:
        append_audit(
            conn,
            "project.bootstrapped",
            actor_id,
            {
                "project_id": project_id,
                "memory_keys": seeded_memory,
                "task_ids": created_task_ids,
            },
        )
    return {"memory_keys": seeded_memory, "task_ids": created_task_ids}
