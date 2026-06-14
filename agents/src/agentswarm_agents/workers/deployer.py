from __future__ import annotations

import argparse
import os
import time
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent


def build_execution_result(request: dict[str, Any]) -> dict[str, Any]:
    target = os.environ.get("AGENTSWARM_DEPLOY_TARGET_URL", "").strip()
    outcome = "simulated"
    message = "Deploy execution recorded (set AGENTSWARM_DEPLOY_TARGET_URL for live target)"
    if target:
        outcome = "target_configured"
        message = f"Deploy target configured: {target}"
    return {
        "request_id": request["request_id"],
        "environment": request["environment"],
        "artifact_ref": request["artifact_ref"],
        "outcome": outcome,
        "message": message,
    }


def fetch_deploy_request(base_url: str, request_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/deploy/requests/{request_id}",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def execute_deploy(base_url: str, request_id: str) -> dict[str, Any]:
    request = fetch_deploy_request(base_url, request_id)
    if request["status"] not in ("approved", "deployed"):
        raise ValueError(f"deploy request {request_id} is {request['status']}")
    return build_execution_result(request)


def run_once(client, base_url: str) -> bool:
    tasks = client.poll_tasks(capability="deployer")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    request_id = task.get("payload", {}).get("request_id")
    if not request_id:
        raise ValueError("deploy.execute task missing request_id")
    result = execute_deploy(base_url, str(request_id))
    client.submit(claim_token, task["task_id"], result)
    print(
        f"deployer: completed {task['task_id']} for {request_id} "
        f"({result['outcome']})"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm deployer agent")
    parser.add_argument("--agent-name", default="deployer")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    base_url = platform_url()
    client = connect_agent(
        agent_name=args.agent_name,
        owner="phase3-deployer",
        capabilities=["deployer"],
        base_url=base_url,
    )
    print(f"deployer: connected as {client.agent_id}")
    if args.once:
        if not run_once(client, base_url):
            print("deployer: no tasks")
        return
    while True:
        if run_once(client, base_url):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
