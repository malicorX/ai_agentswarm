from __future__ import annotations

import argparse
import time
from typing import Any

from agentswarm_agents.client import platform_url
from agentswarm_agents.content.text import classify_topics
from agentswarm_agents.identity import connect_agent

DEFAULT_LABELS = [
    "agents",
    "llm",
    "tools",
    "research",
    "open-source",
    "architecture",
]


def execute_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = task["payload"]
    labels = payload.get("labels") or DEFAULT_LABELS
    if not isinstance(labels, list):
        raise ValueError("labels must be a list")
    draft = payload.get("draft") or {}
    summary = payload.get("summary") or ""
    text = f"{draft.get('title', '')} {summary}"
    label = classify_topics(text, [str(item) for item in labels])
    return {"label": label}


def run_once(client) -> bool:
    tasks = client.poll_tasks(capability="classifier")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = execute_task(task)
    client.submit(claim_token, task["task_id"], result)
    print(f"classifier: completed {task['task_id']} label={result['label']}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm classifier agent")
    parser.add_argument("--agent-name", default="classifier")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    client = connect_agent(
        agent_name=args.agent_name,
        owner="news-classifier",
        capabilities=["classifier"],
        base_url=platform_url(),
    )
    print(f"classifier: connected as {client.agent_id}")
    if args.once:
        if not run_once(client):
            print("classifier: no tasks")
        return
    while True:
        try:
            if run_once(client):
                continue
        except Exception as exc:  # noqa: BLE001
            print(f"classifier: error: {exc}")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
