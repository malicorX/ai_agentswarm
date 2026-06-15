#!/usr/bin/env python3
"""Verify news content pipeline reaches a verified codewriter.add-article task."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

from news_feed_pipeline import DEFAULT_CONFIG, enqueue_news_feeds

_ROOT = Path(__file__).resolve().parent.parent


def verify_news_pipeline(
    base_url: str | None = None,
    *,
    config_path: Path | None = None,
    timeout_sec: float = 240.0,
    enqueue_only: bool = False,
) -> dict[str, str]:
    """Enqueue feed scrapers and optionally wait for a new verified article task."""
    clean = (
        base_url
        or os.environ.get("AGENTSWARM_PLATFORM_URL")
        or os.environ.get("AGENTSWARM_STAGING_API_URL")
        or "http://127.0.0.1:8000"
    ).rstrip("/")

    summary = httpx.get(f"{clean}/platform/summary", timeout=30.0)
    summary.raise_for_status()
    before = summary.json()
    verified_before = int(before.get("tasks", {}).get("verified", 0))

    task_ids = enqueue_news_feeds(clean, config_path=config_path or DEFAULT_CONFIG)
    result: dict[str, str] = {
        "platform_url": clean,
        "verified_before": str(verified_before),
        "enqueued_tasks": str(len(task_ids)),
        "task_ids": ",".join(task_ids),
    }

    if enqueue_only:
        result["mode"] = "enqueue_only"
        return result

    deadline = time.time() + timeout_sec
    last_verified = verified_before
    while time.time() < deadline:
        current = httpx.get(f"{clean}/platform/summary", timeout=30.0).json()
        last_verified = int(current.get("tasks", {}).get("verified", 0))
        if last_verified > verified_before:
            result["mode"] = "verified"
            result["verified_after"] = str(last_verified)
            return result
        time.sleep(3.0)

    tasks = before.get("tasks", {})
    raise RuntimeError(
        "Timed out waiting for pipeline to verify an article task "
        f"(verified stayed at {verified_before}; last poll={last_verified}; "
        f"enqueued={len(task_ids)}; summary.tasks={tasks!r})"
    )


def main() -> int:
    enqueue_only = os.environ.get("AGENTSWARM_VERIFY_NEWS_ENQUEUE_ONLY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        outcome = verify_news_pipeline(enqueue_only=enqueue_only)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"News pipeline verify failed: {exc}", file=sys.stderr)
        return 1
    if outcome.get("mode") == "enqueue_only":
        print(
            f"News pipeline enqueue OK: {outcome['enqueued_tasks']} task(s) "
            f"({outcome['task_ids']})"
        )
    else:
        print(
            "News pipeline OK: "
            f"verified {outcome['verified_before']} -> {outcome['verified_after']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
