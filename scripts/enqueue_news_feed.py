#!/usr/bin/env python3
"""Enqueue scraper.fetch tasks for configured RSS/Atom feeds (P5.2)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers


def load_feed_config(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    feeds = data.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        raise ValueError("config must include non-empty feeds array")
    return feeds


def enqueue_scraper(base_url: str, *, feed: dict) -> dict:
    url = str(feed["url"]).strip()
    response = httpx.post(
        f"{base_url.rstrip('/')}/tasks",
        headers=owner_auth_headers(),
        json={
            "task_type": "scraper.fetch",
            "capability_required": "scraper",
            "payload": {
                "url": url,
                "source": feed.get("source", "feed"),
                "pipeline": True,
                "egress_hosts": feed.get("egress_hosts", []),
            },
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Enqueue news feed scraper tasks")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "config" / "news-feeds.json"),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000"),
    )
    args = parser.parse_args()
    if not owner_auth_headers():
        print("Set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN", file=sys.stderr)
        return 1
    feeds = load_feed_config(Path(args.config))
    created: list[str] = []
    for feed in feeds:
        body = enqueue_scraper(args.base_url, feed=feed)
        task_id = body["task_id"]
        created.append(task_id)
        print(f"enqueued scraper.fetch {task_id} for {feed.get('name', feed['url'])}")
    print(json.dumps({"task_ids": created}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
