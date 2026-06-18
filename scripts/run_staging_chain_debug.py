#!/usr/bin/env python3
"""Run create_task + volunteer workers on staging with visible logs (debug/CI)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))

from agentswarm_agents.create_task import create_goal_from_spec
from agentswarm_agents.engineering_lab import reset_fixture
from agentswarm_agents.engineering_goal import build_engineering_roles
from agentswarm_agents.task_file import load_task_file
from agentswarm_agents.volunteer_client import VolunteerClient, VolunteerConfig
from agentswarm_agents.volunteer_team import goal_auth_headers, wait_for_goal

DEFAULT_BASE = "https://theebie.de/agentswarm/api"
HOST = os.environ.get("AGENTSWARM_THEEBIE_HOST", "root@theebie.de")
ENVFILE = os.environ.get("AGENTSWARM_PLATFORM_ENV_FILE", "/etc/agentswarm/platform.env")


def _ssh_env(key: str) -> str:
    existing = os.environ.get(key, "").strip()
    if existing:
        return existing
    cmd = f"grep -E '^{key}=' {ENVFILE} | cut -d= -f2-"
    value = subprocess.check_output(["ssh", HOST, cmd], text=True).strip().strip("\r")
    os.environ[key] = value
    return value


def _log(role: str, message: str) -> None:
    print(f"[{role}] {message}", flush=True)


def _run_worker(
    base_url: str,
    *,
    capabilities: list[str],
    owner: str,
    model_id: str,
    stop: threading.Event,
    agent_name: str,
) -> None:
    config = VolunteerConfig(
        agent_name=agent_name,
        base_url=base_url,
        owner=owner,
        capabilities=capabilities,
        model_id=model_id,
        wait_timeout_sec=25.0,
        poll_sec=0.5,
        heartbeat_ttl_sec=120,
    )
    volunteer = VolunteerClient(
        config,
        on_log=lambda message, role=owner: _log(role, message),
    )
    volunteer.run_until_stopped(stop)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("AGENTSWARM_STAGING_API_URL", DEFAULT_BASE))
    parser.add_argument("--goal-id", default="", help="Existing goal; if omitted, create from task file")
    parser.add_argument("--task-file", default=str(_ROOT / "tasks" / "example-primes.txt"))
    parser.add_argument("--goal-timeout-sec", type=float, default=240.0)
    parser.add_argument("--model-id", default="llm-mock-v1")
    args = parser.parse_args()

    os.environ.setdefault("AGENTSWARM_REPO_ROOT", str(_ROOT))
    _ssh_env("AGENTSWARM_BOOTSTRAP_TOKEN")
    _ssh_env("AGENTSWARM_ASSIGNMENT_SECRET")

    base_url = args.base_url.rstrip("/")
    run_id = uuid.uuid4().hex[:8]
    stop = threading.Event()
    threads: list[threading.Thread] = []

    for capabilities, owner in build_engineering_roles(run_id, owner_prefix="staging-run"):
        agent_name = f"staging-{'-'.join(capabilities)}-{run_id}"
        thread = threading.Thread(
            target=_run_worker,
            kwargs={
                "base_url": base_url,
                "capabilities": capabilities,
                "owner": owner,
                "model_id": args.model_id,
                "stop": stop,
                "agent_name": agent_name,
            },
            name=f"worker-{'-'.join(capabilities)}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    _log("main", "waiting for workers to connect...")
    time.sleep(6.0)
    headers = goal_auth_headers()
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        cap = client.get(f"{base_url}/dispatch/capacity", headers=headers)
        cap.raise_for_status()
        _log("main", f"capacity: {cap.json().get('totals')}")

    if args.goal_id:
        goal_id = args.goal_id.strip()
        _log("main", f"using existing goal_id={goal_id}")
    else:
        reset_fixture("primes")
        spec = load_task_file(args.task_file)
        created = create_goal_from_spec(base_url, spec)
        goal_id = created["goal_id"]
        _log("main", f"created goal_id={goal_id}")

    try:
        goal = wait_for_goal(base_url, goal_id, timeout_sec=args.goal_timeout_sec, poll_sec=2.0)
    except RuntimeError as exc:
        _log("main", f"FAILED: {exc}")
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            body = client.get(f"{base_url}/creative/goals/{goal_id}").json()
            _log("main", f"final status={body.get('status')}")
        return 1
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=15.0)

    _log("main", f"SUCCESS status={goal.get('status')} goal_id={goal_id}")
    return 0 if goal.get("status") == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
