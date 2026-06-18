#!/usr/bin/env python3
import sqlite3
import sys

gid = sys.argv[1] if len(sys.argv) > 1 else "goal-ac0a7678c8cd"
db = "/var/lib/agentswarm/agentswarm.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
queries = {
    "goal": f"SELECT goal_id,status,goal_kind,created_at FROM creative_goals WHERE goal_id='{gid}'",
    "tasks": f"SELECT task_id,task_type,status,claimed_by,assignment_only FROM tasks WHERE payload LIKE '%{gid}%'",
    "needs": (
        "SELECT need_id,role,status,task_id,assigned_agent_id,lease_id FROM pool_needs "
        f"WHERE task_id IN (SELECT task_id FROM tasks WHERE payload LIKE '%{gid}%')"
    ),
    "leases": (
        "SELECT lease_id,agent_id,task_id,status,expires_at FROM assignment_leases "
        f"WHERE task_id IN (SELECT task_id FROM tasks WHERE payload LIKE '%{gid}%')"
    ),
}
for label, q in queries.items():
    print("==", label)
    rows = conn.execute(q).fetchall()
    if not rows:
        print("(none)")
    for row in rows:
        print(dict(row))
