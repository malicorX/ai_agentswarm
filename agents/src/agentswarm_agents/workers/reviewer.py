from __future__ import annotations

import argparse
import time

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent


def run_once(client) -> bool:
    tasks = client.poll_tasks(capability="reviewer")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    payload = task["payload"]
    test_result = payload.get("test_result", {})
    approved = bool(test_result.get("passed", False))
    result = {
        "approved": approved,
        "notes": "auto-approved after passing tests" if approved else "tests failed",
    }
    client.submit(claim_token, task["task_id"], result)
    print(f"reviewer: completed {task['task_id']} approved={approved}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm reviewer agent")
    parser.add_argument("--agent-name", default="reviewer")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    client = connect_agent(
        agent_name=args.agent_name,
        owner="phase0-reviewer",
        capabilities=["reviewer"],
        base_url=platform_url(),
    )
    print(f"reviewer: connected as {client.agent_id}")

    if args.once:
        if not run_once(client):
            print("reviewer: no tasks")
        return

    while True:
        if run_once(client):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
