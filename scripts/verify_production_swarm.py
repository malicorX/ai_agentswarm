#!/usr/bin/env python3
"""Verify live production swarm processes an enqueued article task (P5.1)."""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers


def _summary(base_url: str, client: httpx.Client) -> dict:
    response = client.get(f"{base_url.rstrip('/')}/platform/summary")
    response.raise_for_status()
    return response.json()


def verify_production_swarm(
    base_url: str,
    *,
    timeout_sec: float = 180.0,
    poll_sec: float = 2.0,
) -> dict[str, int | str]:
    clean = base_url.strip().rstrip("/")
    headers = owner_auth_headers()
    if not headers:
        raise ValueError(
            "Set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN to enqueue tasks"
        )

    article_id = f"swarm-verify-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        before = _summary(clean, client)
        before_verified = int(before.get("tasks", {}).get("verified", 0))

        enqueue = client.post(
            f"{clean}/tasks",
            headers=headers,
            json={
                "task_type": "codewriter.add-article",
                "capability_required": "codewriter",
                "payload": {
                    "article": {
                        "id": article_id,
                        "title": "Production swarm verify",
                        "summary": "Automated P5.1 pipeline check.",
                        "url": "https://example.com/agentswarm-verify",
                        "source": "verify_production_swarm",
                        "published_at": now,
                        "topics": ["agentswarm"],
                    }
                },
            },
        )
        enqueue.raise_for_status()
        task_id = enqueue.json()["task_id"]

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            summary = _summary(clean, client)
            verified = int(summary.get("tasks", {}).get("verified", 0))
            if verified > before_verified:
                return {
                    "task_id": task_id,
                    "article_id": article_id,
                    "verified_before": before_verified,
                    "verified_after": verified,
                }
            time.sleep(poll_sec)

    raise RuntimeError(
        f"timed out waiting for verified count to increase (task {task_id}, article {article_id})"
    )


def main() -> int:
    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        )
    )
    try:
        result = verify_production_swarm(url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Production swarm verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Production swarm OK: {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
