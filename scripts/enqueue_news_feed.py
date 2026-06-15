#!/usr/bin/env python3
"""Enqueue scraper.fetch tasks for configured RSS/Atom feeds (P5.2)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from news_feed_pipeline import enqueue_news_feeds, load_feed_config


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
    config_path = Path(args.config)
    feeds = load_feed_config(config_path)
    try:
        created = enqueue_news_feeds(args.base_url, config_path=config_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for task_id, feed in zip(created, feeds, strict=True):
        print(f"enqueued scraper.fetch {task_id} for {feed.get('name', feed['url'])}")
    print(json.dumps({"task_ids": created}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
