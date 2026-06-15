from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent
from agentswarm_agents.memory_keys import memory_key_for_project
from agentswarm_agents.owner_auth import owner_auth_headers


def detect_gaps(
    summary: dict[str, Any],
    backlog: dict[str, Any] | None,
    *,
    memory_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gaps: list[dict[str, Any]] = []
    enqueue: list[dict[str, Any]] = []
    created = int(summary.get("tasks", {}).get("created", 0))
    articles: list[Any] = []
    if backlog is not None:
        articles = backlog.get("content", {}).get("articles", [])
    if created == 0 and articles:
        gaps.append(
            {
                "type": "idle_pool_with_backlog",
                "article_count": len(articles),
            }
        )
        enqueue.append(
            {
                "task_type": "planner.plan",
                "capability_required": "planner",
                "payload": {
                    "goal": "drain-news-backlog",
                    "memory_key": memory_key,
                },
            }
        )
    failures = summary.get("canary_failures_top") or []
    if failures:
        gaps.append({"type": "canary_failures", "agents": failures})

    deploy = summary.get("deploy_requests") or {}
    by_status = deploy.get("by_status") or {}
    pending_requests = int(by_status.get("pending", 0))
    pending_signoff_tasks = int(deploy.get("pending_signoff_tasks", 0))
    if pending_requests > 0 or pending_signoff_tasks > 0:
        gaps.append(
            {
                "type": "pending_deploy_signoffs",
                "pending_requests": pending_requests,
                "open_signoff_tasks": pending_signoff_tasks,
            }
        )
    approved_waiting = int(by_status.get("approved", 0))
    pending_execute_tasks = int(deploy.get("pending_execute_tasks", 0))
    if approved_waiting > 0 and pending_execute_tasks > 0:
        gaps.append(
            {
                "type": "pending_deploy_execute",
                "approved_requests": approved_waiting,
                "open_execute_tasks": pending_execute_tasks,
            }
        )

    return gaps, enqueue


def execute_scan(base_url: str, project_id: str = "default") -> dict[str, Any]:
    root = base_url.rstrip("/")
    summary = httpx.get(f"{root}/platform/summary", timeout=30.0).json()
    memory_key = memory_key_for_project(project_id)
    backlog = None
    if memory_key in summary.get("memory_keys", []):
        backlog = httpx.get(f"{root}/memory/{memory_key}", timeout=30.0).json()
    gaps, enqueue = detect_gaps(summary, backlog, memory_key=memory_key)
    return {"gaps": gaps, "enqueue": enqueue, "summary": summary, "project_id": project_id}


def record_scan_state(client, project_id: str, result: dict[str, Any]) -> None:
    state_key = memory_key_for_project(project_id, suffix="orchestrator-state")
    try:
        client.upsert_memory(
            state_key,
            {
                "project_id": project_id,
                "gaps": result["gaps"],
                "enqueue_count": len(result["enqueue"]),
                "scanned_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
            tags=["orchestrator"],
        )
    except httpx.HTTPError as exc:
        print(f"orchestrator: could not record scan state ({state_key}): {exc}")


def run_once(client, base_url: str) -> bool:
    tasks = client.poll_tasks(capability="orchestrator")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    project_id = task.get("project_id") or "default"
    result = execute_scan(base_url, project_id=project_id)
    record_scan_state(client, project_id, result)
    client.submit(claim_token, task["task_id"], result)
    print(
        f"orchestrator: completed {task['task_id']} "
        f"({len(result['gaps'])} gaps, {len(result['enqueue'])} actions)"
    )
    return True


def ensure_scan_task(base_url: str, project_id: str = "default") -> None:
    """Maintainer helper: enqueue a scan task if none are pending."""
    headers = owner_auth_headers()
    if not headers:
        return
    response = httpx.post(
        f"{base_url.rstrip('/')}/tasks",
        headers=headers,
        json={
            "task_type": "orchestrator.scan",
            "capability_required": "orchestrator",
            "payload": {"reason": "periodic-gap-check"},
            "project_id": project_id,
        },
        timeout=30.0,
    )
    if response.status_code == 200:
        print(f"orchestrator: enqueued scan task {response.json()['task_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm orchestrator agent")
    parser.add_argument("--agent-name", default="orchestrator")
    parser.add_argument("--project-id", default="default")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--enqueue-scan", action="store_true")
    args = parser.parse_args()
    base_url = platform_url()
    if args.enqueue_scan:
        ensure_scan_task(base_url, project_id=args.project_id)
        return
    client = connect_agent(
        agent_name=args.agent_name,
        owner="phase3-orchestrator",
        capabilities=["orchestrator"],
        base_url=base_url,
    )
    print(f"orchestrator: connected as {client.agent_id}")
    if args.once:
        if not run_once(client, base_url):
            print("orchestrator: no tasks")
        return
    while True:
        if run_once(client, base_url):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
