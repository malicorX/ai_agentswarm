#!/usr/bin/env python3
"""Inspect staging DB for a goal's pool needs and tasks (via SSH)."""

from __future__ import annotations

import json
import subprocess
import sys

GOAL_ID = sys.argv[1] if len(sys.argv) > 1 else "goal-ac0a7678c8cd"
HOST = "root@theebie.de"
DB = "/opt/agentswarm/platform/data/agentswarm.db"


def _sql(query: str) -> str:
    cmd = f'sqlite3 -json {DB} "{query}"'
    return subprocess.check_output(["ssh", HOST, cmd], text=True)


def main() -> None:
    print("=== creative_goals ===")
    print(_sql(
        f"SELECT goal_id, status, goal_kind, created_at FROM creative_goals WHERE goal_id='{GOAL_ID}'"
    ))
    print("=== coordinator tasks (payload contains goal) ===")
    print(_sql(
        "SELECT task_id, task_type, status, claimed_by, assignment_only, created_at "
        f"FROM tasks WHERE payload LIKE '%{GOAL_ID}%' ORDER BY created_at"
    )[:4000])
    print("=== pool_needs for those tasks ===")
    print(_sql(
        "SELECT need_id, role, capability_required, status, task_id, assigned_agent_id, created_at "
        f"FROM pool_needs WHERE task_id IN (SELECT task_id FROM tasks WHERE payload LIKE '%{GOAL_ID}%')"
    ))
    print("=== active leases ===")
    print(_sql(
        "SELECT lease_id, agent_id, task_id, status, expires_at FROM assignment_leases "
        f"WHERE task_id IN (SELECT task_id FROM tasks WHERE payload LIKE '%{GOAL_ID}%')"
    ))
    print("=== recent idle coordinators (sample) ===")
    print(_sql(
        "SELECT p.agent_id, p.status, a.owner, p.model_id FROM agent_presence p "
        "JOIN agents a ON a.agent_id=p.agent_id WHERE p.status='idle' LIMIT 10"
    ))


if __name__ == "__main__":
    main()
