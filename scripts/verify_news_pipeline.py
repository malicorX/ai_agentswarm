#!/usr/bin/env python3
"""Verify news content pipeline reaches a verified codewriter.add-article task."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    base = os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000").rstrip("/")
    if not owner_auth_headers():
        print("Set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN", file=sys.stderr)
        return 1

    before = httpx.get(f"{base}/platform/summary", timeout=30.0).json()
    verified_before = int(before.get("tasks", {}).get("verified", 0))

    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "enqueue_news_feed.py"), "--base-url", base],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode

    deadline = time.time() + 240.0
    while time.time() < deadline:
        summary = httpx.get(f"{base}/platform/summary", timeout=30.0).json()
        verified = int(summary.get("tasks", {}).get("verified", 0))
        if verified > verified_before:
            print(f"News pipeline OK: verified {verified_before} -> {verified}")
            return 0
        time.sleep(3.0)

    print("Timed out waiting for pipeline to verify an article task", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
