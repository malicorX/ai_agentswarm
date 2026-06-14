from __future__ import annotations

import json
import re
import sqlite3
import uuid
from typing import Any, Callable

from agentswarm_platform.governance_templates import resolve_governance_config
from agentswarm_platform.models import utc_now_iso

DEFAULT_PROJECT_ID = "default"
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


def validate_project_id(project_id: str) -> str:
    normalized = project_id.strip().lower()
    if not _PROJECT_ID_RE.match(normalized):
        raise ValueError(
            "invalid project_id (use lowercase letters, digits, hyphens; start with a letter)"
        )
    return normalized


def ensure_projects_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_projects (
            agent_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (agent_id, project_id)
        );
        """
    )
    project_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()
    }
    if "governance_template_id" not in project_columns:
        conn.execute("ALTER TABLE projects ADD COLUMN governance_template_id TEXT")
    if "governance_config" not in project_columns:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN governance_config TEXT NOT NULL DEFAULT '{}'"
        )
    row = conn.execute(
        "SELECT 1 FROM projects WHERE project_id = ?", (DEFAULT_PROJECT_ID,)
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO projects (
                project_id, name, description, created_at,
                governance_template_id, governance_config
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_PROJECT_ID,
                "Default",
                "Built-in project for single-swarm deployments",
                utc_now_iso(),
                None,
                json.dumps({}),
            ),
        )


def _project_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    governance_config_raw = (
        row["governance_config"] if "governance_config" in keys else "{}"
    )
    try:
        governance_config = json.loads(governance_config_raw or "{}")
    except json.JSONDecodeError:
        governance_config = {}
    if not isinstance(governance_config, dict):
        governance_config = {}
    return {
        "project_id": row["project_id"],
        "name": row["name"],
        "description": row["description"],
        "created_at": row["created_at"],
        "governance_template_id": row["governance_template_id"]
        if "governance_template_id" in keys
        else None,
        "governance_config": governance_config,
    }


def get_project(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM projects WHERE project_id = ?", (project_id,)
    ).fetchone()
    if row is None:
        return None
    return _project_row_to_dict(row)


def list_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at ASC").fetchall()
    return [_project_row_to_dict(row) for row in rows]


def create_project(
    conn: sqlite3.Connection,
    *,
    name: str,
    description: str | None,
    project_id: str | None,
    governance_template_id: str | None = None,
    append_audit: Callable[[sqlite3.Connection, str, str | None, dict[str, Any]], None],
    actor_id: str | None = None,
    apply_bootstrap: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_id = validate_project_id(project_id or f"proj-{uuid.uuid4().hex[:12]}")
    if get_project(conn, resolved_id) is not None:
        raise ValueError(f"project already exists: {resolved_id}")
    template_id, governance_config = resolve_governance_config(governance_template_id)
    created_at = utc_now_iso()
    conn.execute(
        """
        INSERT INTO projects (
            project_id, name, description, created_at,
            governance_template_id, governance_config
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            resolved_id,
            name.strip(),
            description,
            created_at,
            template_id,
            json.dumps(governance_config),
        ),
    )
    append_audit(
        conn,
        "project.created",
        actor_id,
        {
            "project_id": resolved_id,
            "name": name.strip(),
            "governance_template_id": template_id,
        },
    )
    bootstrap_result = {"memory_keys": [], "task_ids": []}
    if apply_bootstrap is not None and governance_config:
        bootstrap_result = apply_bootstrap(
            conn,
            project_id=resolved_id,
            governance_config=governance_config,
            actor_id=actor_id,
            append_audit=append_audit,
        )
    project = _project_row_to_dict(
        conn.execute("SELECT * FROM projects WHERE project_id = ?", (resolved_id,)).fetchone()
    )
    project["bootstrap"] = bootstrap_result
    return project


def join_agent_to_project(
    conn: sqlite3.Connection, agent_id: str, project_id: str
) -> None:
    if get_project(conn, project_id) is None:
        raise ValueError(f"unknown project: {project_id}")
    conn.execute(
        """
        INSERT OR IGNORE INTO agent_projects (agent_id, project_id, joined_at)
        VALUES (?, ?, ?)
        """,
        (agent_id, project_id, utc_now_iso()),
    )


def agent_project_ids(conn: sqlite3.Connection, agent_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT project_id FROM agent_projects WHERE agent_id = ?", (agent_id,)
    ).fetchall()
    if rows:
        return {row["project_id"] for row in rows}
    return {DEFAULT_PROJECT_ID}