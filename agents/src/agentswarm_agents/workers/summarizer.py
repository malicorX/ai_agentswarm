from __future__ import annotations

import argparse
import time
from typing import Any

from agentswarm_agents.client import platform_url
from agentswarm_agents.content.text import summarize_text
from agentswarm_agents.identity import connect_agent


def execute_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = task["payload"]
    draft = payload.get("draft")
    if not isinstance(draft, dict):
        raise ValueError("summarizer.summarize requires payload.draft")
    raw_text = str(draft.get("raw_text", "")).strip()
    if not raw_text:
        raise ValueError("draft.raw_text is required")
    return {"summary": summarize_text(raw_text), "draft": draft}


def run_once(client) -> bool:
    tasks = client.poll_tasks(capability="summarizer")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = execute_task(task)
    client.submit(claim_token, task["task_id"], result)
    print(f"summarizer: completed {task['task_id']}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm summarizer agent")
    parser.add_argument("--agent-name", default="summarizer")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    client = connect_agent(
        agent_name=args.agent_name,
        owner="news-summarizer",
        capabilities=["summarizer"],
        base_url=platform_url(),
    )
    print(f"summarizer: connected as {client.agent_id}")
    if args.once:
        if not run_once(client):
            print("summarizer: no tasks")
        return
    while True:
        try:
            if run_once(client):
                continue
        except Exception as exc:  # noqa: BLE001
            print(f"summarizer: error: {exc}")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
