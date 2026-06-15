"""Shared news feed enqueue helpers (P5.2 / P21.1)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "news-feeds.json"


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


def enqueue_news_feeds(
    base_url: str,
    *,
    config_path: Path | None = None,
) -> list[str]:
    if not owner_auth_headers():
        raise RuntimeError("Set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN")
    feeds = load_feed_config(config_path or DEFAULT_CONFIG)
    task_ids: list[str] = []
    for feed in feeds:
        body = enqueue_scraper(base_url, feed=feed)
        task_ids.append(str(body["task_id"]))
    return task_ids
