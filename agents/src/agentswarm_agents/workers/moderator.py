from __future__ import annotations

import argparse
import time
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent
from agentswarm_agents.owner_auth import owner_auth_headers


def build_moderation_actions(summary: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    for entry in summary.get("canary_failures_top") or []:
        attempts = int(entry.get("attempts", 0))
        failures = int(entry.get("failures", 0))
        if attempts < 2:
            continue
        failure_rate = failures / attempts
        agent_id = entry["agent_id"]
        if failure_rate >= 0.5:
            findings.append(
                {
                    "type": "canary_failure_rate",
                    "agent_id": agent_id,
                    "failure_rate": round(failure_rate, 3),
                    "attempts": attempts,
                }
            )
            actions.append(
                {
                    "type": "quarantine",
                    "agent_id": agent_id,
                    "reason": f"canary failure rate {failure_rate:.0%} over {attempts} attempts",
                }
            )
        elif failures > 0:
            findings.append(
                {
                    "type": "canary_failures",
                    "agent_id": agent_id,
                    "failures": failures,
                }
            )
            actions.append(
                {
                    "type": "flag",
                    "subject_type": "agent",
                    "subject_id": agent_id,
                    "reason": "elevated canary failures",
                    "severity": "medium",
                    "details": entry,
                }
            )

    disputed = int(summary.get("replication_groups", {}).get("disputed", 0))
    if disputed > 0:
        findings.append({"type": "disputed_replications", "count": disputed})
        actions.append(
            {
                "type": "flag",
                "subject_type": "platform",
                "subject_id": "replication",
                "reason": f"{disputed} disputed replication group(s) need review",
                "severity": "medium",
                "details": {"disputed_count": disputed},
            }
        )

    return findings, actions


def execute_scan(base_url: str) -> dict[str, Any]:
    summary = httpx.get(f"{base_url.rstrip('/')}/platform/summary", timeout=30.0).json()
    findings, actions = build_moderation_actions(summary)
    return {"findings": findings, "actions": actions}


def run_once(client, base_url: str) -> bool:
    tasks = client.poll_tasks(capability="moderator")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = execute_scan(base_url)
    client.submit(claim_token, task["task_id"], result)
    print(
        f"moderator: completed {task['task_id']} "
        f"({len(result['findings'])} findings, {len(result['actions'])} actions)"
    )
    return True


def ensure_scan_task(base_url: str) -> None:
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
        },
        timeout=30.0,
    )
    if response.status_code == 200:
        print(f"moderator: enqueued scan task {response.json()['task_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm moderator agent")
    parser.add_argument("--agent-name", default="moderator")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--enqueue-scan", action="store_true")
    args = parser.parse_args()
    base_url = platform_url()
    if args.enqueue_scan:
        ensure_scan_task(base_url)
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
