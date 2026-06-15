#!/usr/bin/env python3
"""Enqueue a task on the AgentSwarm platform (Phase 0 maintainer tool)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers


def main() -> None:
    parser = argparse.ArgumentParser(description="Enqueue AgentSwarm tasks")
    sub = parser.add_subparsers(dest="command", required=True)

    patch = sub.add_parser("patch", help="Enqueue codewriter.patch")
    patch.add_argument("--file", default="index.html")
    patch.add_argument("--insert", required=True)

    article = sub.add_parser("add-article", help="Enqueue codewriter.add-article")
    article.add_argument("--id", required=True)
    article.add_argument("--title", required=True)
    article.add_argument("--summary", required=True)
    article.add_argument("--url", required=True)
    article.add_argument("--source", required=True)
    article.add_argument("--topics", default="", help="Comma-separated topics")
    article.add_argument("--published-at", dest="published_at", default=None)
    article.add_argument(
        "--bounty",
        type=float,
        default=None,
        help="Extra credibility bonus on verified acceptance",
    )

    args = parser.parse_args()
    base_url = os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000")

    if args.command == "patch":
        body: dict[str, Any] = {
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {"file": args.file, "insert": args.insert},
        }
    else:
        topics = [t.strip() for t in args.topics.split(",") if t.strip()]
        published_at = args.published_at or datetime.now(timezone.utc).replace(
            microsecond=0
        ).isoformat()
        body = {
            "task_type": "codewriter.add-article",
            "capability_required": "codewriter",
            "payload": {
                "article": {
                    "id": args.id,
                    "title": args.title,
                    "summary": args.summary,
                    "url": args.url,
                    "source": args.source,
                    "published_at": published_at,
                    "topics": topics,
                }
            },
        }
        if args.bounty is not None:
            body["payload"]["bounty"] = {"credibility_bonus": args.bounty}

    response = httpx.post(
        f"{base_url.rstrip('/')}/tasks",
        json=body,
        headers=owner_auth_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        print(f"enqueue failed: {exc}", file=sys.stderr)
        sys.exit(1)
