from __future__ import annotations

import argparse
import time
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent
from agentswarm_agents.owner_auth import owner_auth_headers
from agentswarm_platform.moderation_policy import (
    build_moderation_actions,
    resolve_moderation_policy,
)


def fetch_project_governance(base_url: str, project_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/projects/{project_id}/governance",
        timeout=30.0,
    )
    if response.status_code != 200:
        return {}
    body = response.json()
    config = body.get("governance_config")
    return config if isinstance(config, dict) else {}


def execute_scan(base_url: str, project_id: str = "default") -> dict[str, Any]:
    summary = httpx.get(f"{base_url.rstrip('/')}/platform/summary", timeout=30.0).json()
    governance = fetch_project_governance(base_url, project_id)
    policy = resolve_moderation_policy(governance)
    findings, actions = build_moderation_actions(summary, policy)
    return {
        "project_id": project_id,
        "findings": findings,
        "actions": actions,
        "policy": {
            "canary_failure_rate_threshold": policy.canary_failure_rate_threshold,
            "min_canary_attempts": policy.min_canary_attempts,
            "flag_deploy_backlog": policy.flag_deploy_backlog,
        },
    }


def run_once(client, base_url: str) -> bool:
    tasks = client.poll_tasks(capability="moderator")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    project_id = task.get("project_id") or "default"
    result = execute_scan(base_url, project_id=project_id)
    client.submit(claim_token, task["task_id"], result)
    print(
        f"moderator: completed {task['task_id']} "
        f"({len(result['findings'])} findings, {len(result['actions'])} actions)"
    )
    return True


def ensure_scan_task(base_url: str, project_id: str = "default") -> None:
    headers = owner_auth_headers()
    if not headers:
        return
    response = httpx.post(
        f"{base_url.rstrip('/')}/tasks",
        headers=headers,
        json={
            "task_type": "moderator.scan",
            "capability_required": "moderator",
            "payload": {"reason": "periodic-moderation"},
            "project_id": project_id,
        },
        timeout=30.0,
    )
    if response.status_code == 200:
        print(f"moderator: enqueued scan task {response.json()['task_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm moderator agent")
    parser.add_argument("--agent-name", default="moderator")
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
        owner="phase3-moderator",
        capabilities=["moderator"],
        base_url=base_url,
    )
    print(f"moderator: connected as {client.agent_id}")
    if args.once:
        if not run_once(client, base_url):
            print("moderator: no tasks")
        return
    while True:
        if run_once(client, base_url):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
