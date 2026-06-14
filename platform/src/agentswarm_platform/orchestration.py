from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import sqlite3

from agentswarm_platform.models import TaskStatus, utc_now_iso


def validate_enqueue_spec(item: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    task_type = item.get("task_type")
    capability_required = item.get("capability_required")
    payload = item.get("payload")
    if not isinstance(task_type, str) or not task_type.strip():
        raise ValueError("enqueue item requires task_type")
    if not isinstance(capability_required, str) or not capability_required.strip():
        raise ValueError("enqueue item requires capability_required")
    if not isinstance(payload, dict):
        raise ValueError("enqueue item requires payload object")
    return task_type, capability_required, payload


def enqueue_child_tasks(
    conn: sqlite3.Connection,
    *,
    parent_task_id: str,
    specs: list[dict[str, Any]],
    trigger: str,
    append_audit: Callable[[sqlite3.Connection, str, str | None, dict[str, Any]], None],
    project_id: str = "default",
) -> list[str]:
    created_at = utc_now_iso()
    task_ids: list[str] = []
    for spec in specs:
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
                parent_task_id,
                None,
                created_at,
                project_id,
            ),
        )
        task_ids.append(task_id)
        append_audit(
            conn,
            "task.created",
            None,
            {
                "task_id": task_id,
                "task_type": task_type,
                "trigger": trigger,
                "parent_task_id": parent_task_id,
                "project_id": project_id,
            },
        )
    return task_ids
