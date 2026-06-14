from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from agentswarm_agents.client import pilot_dir, platform_url
from agentswarm_agents.identity import connect_agent

REQUIRED_ARTICLE_FIELDS = ("id", "title", "summary", "url", "source", "published_at")


def apply_patch(payload: dict) -> dict:
    rel_path = payload["file"]
    marker = payload.get("marker", "<!-- agentswarm -->")
    target = Path(pilot_dir()) / rel_path
    if not target.exists():
        raise FileNotFoundError(f"pilot file not found: {target}")
    content = target.read_text(encoding="utf-8")
    if marker in content:
        new_content = content.replace(marker, f"{marker}\n{payload.get('insert', '')}")
    else:
        new_content = content + f"\n{marker}\n{payload.get('insert', '')}\n"
    target.write_text(new_content, encoding="utf-8")
    return {"file": rel_path, "applied": True, "bytes_written": len(new_content)}


def validate_article(article: dict[str, Any]) -> None:
    for field in REQUIRED_ARTICLE_FIELDS:
        if field not in article or not str(article[field]).strip():
            raise ValueError(f"article missing required field: {field}")
    if not isinstance(article.get("topics", []), list):
        raise ValueError("article.topics must be a list")


def add_article(payload: dict) -> dict:
    article = payload.get("article")
    if not isinstance(article, dict):
        raise ValueError("payload.article must be an object")
    validate_article(article)
    if "topics" not in article:
        article = {**article, "topics": []}

    data_path = Path(pilot_dir()) / "data" / "articles.json"
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
    else:
        data = {"articles": []}

    articles: list[dict[str, Any]] = data.get("articles", [])
    if any(a.get("id") == article["id"] for a in articles):
        raise ValueError(f"duplicate article id: {article['id']}")

    articles.append(article)
    data["articles"] = articles
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "article_id": article["id"],
        "applied": True,
        "article_count": len(articles),
    }


def execute_task(task: dict) -> dict:
    task_type = task["task_type"]
    payload = task["payload"]
    if task_type == "codewriter.patch":
        return apply_patch(payload)
    if task_type == "codewriter.add-article":
        return add_article(payload)
    raise ValueError(f"unsupported task type: {task_type}")


def run_once(client) -> bool:
    tasks = client.poll_tasks(capability="codewriter")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = execute_task(task)
    client.submit(claim_token, task["task_id"], result)
    print(f"codewriter: completed {task['task_id']} ({task['task_type']})")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm codewriter agent")
    parser.add_argument("--agent-name", default="codewriter")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    client = connect_agent(
        agent_name=args.agent_name,
        owner="phase0-codewriter",
        capabilities=["codewriter"],
        base_url=platform_url(),
    )
    print(f"codewriter: connected as {client.agent_id}")

    if args.once:
        if not run_once(client):
            print("codewriter: no tasks")
        return

    while True:
        if run_once(client):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
