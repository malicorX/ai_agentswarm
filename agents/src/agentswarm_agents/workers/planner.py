from __future__ import annotations

import argparse
import time
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent
from agentswarm_agents.memory_keys import memory_key_for_project


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


def should_clear_backlog_after_plan(goal: str, planned_count: int) -> bool:
    return planned_count > 0 and goal in ("drain-news-backlog", "drain")


def execute_task(task: dict[str, Any], base_url: str, client=None) -> dict[str, Any]:
    payload = task["payload"]
    memory_key = memory_key_for_project(
        task.get("project_id"),
        explicit_key=payload.get("memory_key"),
    )
    goal = payload.get("goal", "plan")
    response = httpx.get(f"{base_url.rstrip('/')}/memory/{memory_key}", timeout=30.0)
    response.raise_for_status()
    result = build_enqueue_from_backlog(response.json(), goal)
    if client is not None and should_clear_backlog_after_plan(goal, result["planned_count"]):
        client.upsert_memory(
            memory_key,
            {"articles": []},
            tags=["planner", "backlog-drained"],
        )
        result["backlog_cleared"] = True
    return result


def run_once(client, base_url: str) -> bool:
    tasks = client.poll_tasks(capability="planner")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = execute_task(task, base_url, client=client)
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
