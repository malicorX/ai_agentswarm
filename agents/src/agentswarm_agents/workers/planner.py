from __future__ import annotations

import argparse
import time
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent


def build_enqueue_from_backlog(entry: dict[str, Any], goal: str) -> dict[str, Any]:
    articles = entry.get("content", {}).get("articles", [])
    if not isinstance(articles, list):
        raise ValueError("news-backlog content.articles must be a list")
    enqueue = [
        {
            "task_type": "codewriter.add-article",
            "capability_required": "codewriter",
            "payload": {"article": article},
        }
        for article in articles
        if isinstance(article, dict)
    ]
    return {
        "goal": goal,
        "enqueue": enqueue,
        "planned_count": len(enqueue),
    }


def execute_task(task: dict[str, Any], base_url: str) -> dict[str, Any]:
    payload = task["payload"]
    memory_key = payload.get("memory_key", "news-backlog")
    goal = payload.get("goal", "plan")
    response = httpx.get(f"{base_url.rstrip('/')}/memory/{memory_key}", timeout=30.0)
    response.raise_for_status()
    return build_enqueue_from_backlog(response.json(), goal)


def run_once(client, base_url: str) -> bool:
    tasks = client.poll_tasks(capability="planner")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = execute_task(task, base_url)
    client.submit(claim_token, task["task_id"], result)
    print(
        f"planner: completed {task['task_id']} "
        f"(enqueued {result['planned_count']} tasks for {result['goal']})"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm planner agent")
    parser.add_argument("--agent-name", default="planner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    base_url = platform_url()
    client = connect_agent(
        agent_name=args.agent_name,
        owner="phase3-planner",
        capabilities=["planner"],
        base_url=base_url,
    )
    print(f"planner: connected as {client.agent_id}")
    if args.once:
        if not run_once(client, base_url):
            print("planner: no tasks")
        return
    while True:
        if run_once(client, base_url):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
