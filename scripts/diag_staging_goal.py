#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys

import httpx

GOAL_ID = sys.argv[1] if len(sys.argv) > 1 else "goal-a8046c5ed5d5"
HOST = os.environ.get("AGENTSWARM_THEEBIE_HOST", "root@theebie.de")
ENVFILE = os.environ.get("AGENTSWARM_PLATFORM_ENV_FILE", "/etc/agentswarm/platform.env")
BASE = os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api")


def _ssh_grep(key: str) -> str:
    cmd = f"grep -E '^{key}=' {ENVFILE} | cut -d= -f2-"
    return subprocess.check_output(["ssh", HOST, cmd], text=True).strip().strip("\r")


def main() -> int:
    boot = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN") or _ssh_grep("AGENTSWARM_BOOTSTRAP_TOKEN")
    headers = {"X-Bootstrap-Token": boot}
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        cfg = client.get(f"{BASE}/platform/config", headers=headers)
        goal = client.get(f"{BASE}/creative/goals/{GOAL_ID}")
        cap = client.get(f"{BASE}/dispatch/capacity", headers=headers)
    print("config_status", cfg.status_code)
    print("goal_status_code", goal.status_code)
    if goal.status_code == 200:
        body = goal.json()
        print("goal", json.dumps({k: body.get(k) for k in ("goal_id", "status", "goal_kind", "brief")}, indent=2))
    else:
        print(goal.text)
    print("capacity_status", cap.status_code)
    if cap.status_code == 200:
        print("capacity", json.dumps(cap.json(), indent=2)[:2000])
    cfg_body = cfg.json()
    print("assignment", cfg_body.get("assignment"))
    print("models", cfg_body.get("models"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
