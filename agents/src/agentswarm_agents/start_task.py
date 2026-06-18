"""Run volunteer workers against a queued goal until it reaches a terminal status."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.create_task import create_goal_from_spec
from agentswarm_agents.engineering_goal import ENGINEERING_ROLE_NAMES, build_engineering_roles
from agentswarm_agents.engineering_lab import reset_fixture
from agentswarm_agents.task_file import TaskSpec, load_task_file
from agentswarm_agents.volunteer_client import VolunteerClient, VolunteerConfig
from agentswarm_agents.volunteer_capabilities import default_generalist_capabilities
from agentswarm_agents.volunteer_team import (
    TERMINAL_GOAL_STATUSES,
    clean_platform_url,
    goal_auth_headers,
    validate_dispatch_platform,
    wait_for_goal,
)


def sandbox_tester_enabled(
    *,
    spec: TaskSpec | None = None,
    goal: dict[str, Any] | None = None,
) -> bool:
    if os.environ.get("AGENTSWARM_SANDBOX", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    if spec is not None and spec.workspace_mode == "sandbox":
        return True
    if goal is not None:
        verification_spec = goal.get("verification_spec") or {}
        if verification_spec.get("workspace_mode") == "sandbox":
            return True
    return False


def windows_sandbox_enabled(
    *,
    spec: TaskSpec | None = None,
    goal: dict[str, Any] | None = None,
) -> bool:
    if os.environ.get("AGENTSWARM_WINDOWS_SANDBOX", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return True
    if spec is not None and spec.workspace_mode == "windows":
        return True
    if goal is not None:
        verification_spec = goal.get("verification_spec") or {}
        if verification_spec.get("workspace_mode") == "windows":
            return True
    return False


def engineering_roles_for_run(
    run_id: str,
    *,
    owner_prefix: str = "start",
    spec: TaskSpec | None = None,
    goal: dict[str, Any] | None = None,
) -> list[tuple[list[str], str]]:
    linux_sandbox = sandbox_tester_enabled(spec=spec, goal=goal)
    windows_sandbox = windows_sandbox_enabled(spec=spec, goal=goal)
    return build_engineering_roles(
        run_id,
        owner_prefix=owner_prefix,
        sandbox_tester=linux_sandbox,
        sandbox_builder=linux_sandbox,
        windows_sandbox_tester=windows_sandbox,
        windows_sandbox_builder=windows_sandbox,
    )


def realign_goal_to_team(
    base_url: str,
    goal_id: str,
    include_owners: list[str],
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    clean = clean_platform_url(base_url)
    headers = goal_auth_headers()
    if not headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN to realign goal dispatch"
        )
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.post(
            f"{clean}/creative/goals/{goal_id}/realign-dispatch",
            json={"include_owners": include_owners},
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


def run_volunteer_worker_until_stopped(
    base_url: str,
    *,
    capabilities: list[str],
    owner: str,
    model_id: str,
    wait_timeout_sec: float,
    stop: threading.Event,
    agent_name_prefix: str = "start",
) -> None:
    suffix = uuid.uuid4().hex[:8]
    config = VolunteerConfig(
        agent_name=f"{agent_name_prefix}-{'-'.join(capabilities)}-{suffix}",
        base_url=clean_platform_url(base_url),
        owner=owner,
        capabilities=capabilities,
        model_id=model_id,
        wait_timeout_sec=wait_timeout_sec,
        poll_sec=0.5,
        heartbeat_ttl_sec=120,
    )
    volunteer = VolunteerClient(
        config,
        on_log=lambda message, role=owner: print(f"[{role}] {message}", flush=True),
    )
    volunteer.run_until_stopped(stop)


def start_engineering_volunteer_threads(
    base_url: str,
    *,
    roles: list[tuple[list[str], str]],
    stop: threading.Event,
    model_id: str,
    wait_timeout_sec: float,
    agent_name_prefix: str = "start",
) -> list[threading.Thread]:
    threads: list[threading.Thread] = []
    for capabilities, owner in roles:
        thread = threading.Thread(
            target=run_volunteer_worker_until_stopped,
            kwargs={
                "base_url": base_url,
                "capabilities": capabilities,
                "owner": owner,
                "model_id": model_id,
                "wait_timeout_sec": wait_timeout_sec,
                "stop": stop,
                "agent_name_prefix": agent_name_prefix,
            },
            name=f"start-{'-'.join(capabilities)}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)
    return threads


def wait_for_team_workers_ready(
    base_url: str,
    roles: list[tuple[list[str], str]],
    *,
    timeout_sec: float = 45.0,
    poll_sec: float = 0.5,
    warmup_sec: float = 3.0,
) -> dict[str, Any]:
    """Wait until each role owner is idle on /dispatch/capacity."""
    clean = clean_platform_url(base_url)
    headers = goal_auth_headers()
    deadline = time.monotonic() + timeout_sec
    last_body: dict[str, Any] = {}

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        probe = client.get(f"{clean}/dispatch/capacity", headers=headers)
        if probe.status_code == 404:
            print(
                "note: /dispatch/capacity not on platform yet; waiting for worker warmup",
                file=sys.stderr,
            )
            time.sleep(warmup_sec)
            return {}
        if probe.status_code == 401:
            raise RuntimeError(
                "dispatch/capacity requires AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN"
            )
        probe.raise_for_status()

        while time.monotonic() < deadline:
            response = client.get(f"{clean}/dispatch/capacity", headers=headers)
            response.raise_for_status()
            last_body = response.json()
            caps = last_body.get("capabilities", {})
            ready = True
            for capabilities, owner in roles:
                capability = capabilities[0]
                bucket = caps.get(capability, {})
                agents = bucket.get("agents", [])
                if not any(
                    agent.get("owner") == owner and agent.get("status") == "idle"
                    for agent in agents
                ):
                    ready = False
                    break
            if ready:
                return last_body
            time.sleep(poll_sec)

    missing: list[str] = []
    caps = last_body.get("capabilities", {})
    for capabilities, owner in roles:
        capability = capabilities[0]
        bucket = caps.get(capability, {})
        agents = bucket.get("agents", [])
        if not any(
            agent.get("owner") == owner and agent.get("status") == "idle"
            for agent in agents
        ):
            missing.append(f"{capability}:{owner}")
    raise RuntimeError(
        f"volunteer team not ready within {timeout_sec}s; missing idle: {', '.join(missing)}"
    )


def fetch_goal_status(base_url: str, goal_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    clean = clean_platform_url(base_url)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(f"{clean}/creative/goals/{goal_id}")
        response.raise_for_status()
        return response.json()


def execute_goal_with_volunteers(
    base_url: str,
    goal_id: str,
    *,
    roles: list[tuple[list[str], str]] | None = None,
    model_id: str | None = None,
    wait_timeout_sec: float = 15.0,
    goal_timeout_sec: float = 180.0,
    worker_ready_timeout_sec: float = 45.0,
    owner_prefix: str = "start",
    wait_for_workers: bool = True,
    realign_dispatch: bool = True,
) -> dict[str, Any]:
    """Run an engineering volunteer team until goal_id is verified or rejected."""
    clean = clean_platform_url(base_url)
    existing = fetch_goal_status(clean, goal_id)
    existing_status = str(existing.get("status", ""))
    if existing_status in TERMINAL_GOAL_STATUSES:
        if existing_status == "verified":
            print(f"goal {goal_id} already verified", flush=True)
            return existing
        raise RuntimeError(
            f"goal {goal_id} already terminal (status={existing_status!r})"
        )

    team_roles = roles or engineering_roles_for_run(
        uuid.uuid4().hex[:8],
        owner_prefix=owner_prefix,
        goal=existing,
    )
    include_owners = [owner for _caps, owner in team_roles]

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        config_body = config.json()

    resolved_model = model_id or validate_dispatch_platform(config_body)
    dispatch = config_body.get("dispatch")
    if isinstance(dispatch, dict) and dispatch.get("long_poll_max_sec"):
        max_wait = float(dispatch["long_poll_max_sec"])
        if wait_timeout_sec > max_wait:
            wait_timeout_sec = max_wait

    stop = threading.Event()
    threads = start_engineering_volunteer_threads(
        clean,
        roles=team_roles,
        stop=stop,
        model_id=resolved_model,
        wait_timeout_sec=wait_timeout_sec,
    )
    try:
        if wait_for_workers:
            wait_for_team_workers_ready(
                clean,
                team_roles,
                timeout_sec=worker_ready_timeout_sec,
            )
        if realign_dispatch:
            current = fetch_goal_status(clean, goal_id)
            if str(current.get("status", "")) not in TERMINAL_GOAL_STATUSES:
                result = realign_goal_to_team(clean, goal_id, include_owners)
                print(
                    f"realign: reclaimed={len(result.get('reclaimed_need_ids', []))} "
                    f"redispatched={len(result.get('redispatched_need_ids', []))}",
                    flush=True,
                )
        goal = wait_for_goal(clean, goal_id, timeout_sec=goal_timeout_sec, poll_sec=1.0)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=10.0)
        alive = [thread.name for thread in threads if thread.is_alive()]
        if alive:
            raise RuntimeError(f"volunteer threads did not stop: {', '.join(alive)}")

    if goal.get("status") not in TERMINAL_GOAL_STATUSES:
        raise RuntimeError(f"goal {goal_id} ended in unexpected status {goal.get('status')!r}")
    if goal.get("status") != "verified":
        raise RuntimeError(f"goal {goal_id} not verified (status={goal.get('status')!r})")
    return goal


def execute_goal_with_generalist_volunteer(
    base_url: str,
    goal_id: str,
    *,
    model_id: str | None = None,
    owner: str = "volunteer-e2e",
    wait_timeout_sec: float = 15.0,
    goal_timeout_sec: float = 180.0,
    worker_ready_timeout_sec: float = 45.0,
    realign_dispatch: bool = False,
) -> dict[str, Any]:
    """One generalist volunteer (task-console UX): create goal -> poll -> full pipeline."""
    return execute_goal_with_volunteers(
        base_url,
        goal_id,
        roles=[(default_generalist_capabilities(), owner)],
        model_id=model_id,
        wait_timeout_sec=wait_timeout_sec,
        goal_timeout_sec=goal_timeout_sec,
        worker_ready_timeout_sec=worker_ready_timeout_sec,
        realign_dispatch=realign_dispatch,
    )


def create_and_execute_with_generalist_volunteer(
    base_url: str,
    task_file: str | Path,
    *,
    model_id: str | None = None,
    owner: str = "volunteer-e2e",
    wait_timeout_sec: float = 15.0,
    goal_timeout_sec: float = 180.0,
    worker_ready_timeout_sec: float = 45.0,
) -> dict[str, Any]:
    """Load task file, post goal, run one generalist volunteer until verified."""
    spec = load_task_file(task_file)
    created = create_goal_from_spec(base_url, spec)
    return execute_goal_with_generalist_volunteer(
        base_url,
        created["goal_id"],
        model_id=model_id,
        owner=owner,
        wait_timeout_sec=wait_timeout_sec,
        goal_timeout_sec=goal_timeout_sec,
        worker_ready_timeout_sec=worker_ready_timeout_sec,
    )


def create_and_execute_task_file(
    base_url: str,
    task_file: str | Path,
    *,
    model_id: str | None = None,
    wait_timeout_sec: float = 15.0,
    goal_timeout_sec: float = 180.0,
    worker_ready_timeout_sec: float = 45.0,
    owner_prefix: str = "start",
) -> dict[str, Any]:
    spec = load_task_file(task_file)
    run_id = uuid.uuid4().hex[:8]
    team_roles = engineering_roles_for_run(
        run_id,
        owner_prefix=owner_prefix,
        spec=spec,
    )
    include_owners = [owner for _caps, owner in team_roles]

    if spec.fixture:
        reset_fixture(spec.fixture)
    isolated = replace(
        spec,
        dispatch_isolated=True,
        dispatch_include_owners=include_owners,
    )

    clean = clean_platform_url(base_url)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        config_body = config.json()
    resolved_model = model_id or validate_dispatch_platform(config_body)

    stop = threading.Event()
    threads = start_engineering_volunteer_threads(
        clean,
        roles=team_roles,
        stop=stop,
        model_id=resolved_model,
        wait_timeout_sec=wait_timeout_sec,
        agent_name_prefix=owner_prefix,
    )
    try:
        wait_for_team_workers_ready(clean, team_roles, timeout_sec=worker_ready_timeout_sec)
        created = create_goal_from_spec(clean, isolated)
        goal_id = created["goal_id"]
        print(f"created goal_id={goal_id}", flush=True)
        goal = wait_for_goal(clean, goal_id, timeout_sec=goal_timeout_sec, poll_sec=1.0)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=10.0)

    if goal.get("status") != "verified":
        raise RuntimeError(f"goal {goal_id} not verified (status={goal.get('status')!r})")
    return goal


def format_start_task_output(goal: dict[str, Any], *, goal_id: str) -> str:
    lines = [
        f"goal_id={goal_id}",
        f"status={goal.get('status')}",
        "result=verified",
    ]
    if goal.get("artifact_text"):
        lines.append("artifact=present")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentswarm-start-task",
        description="Run volunteer workers until a queued goal is verified.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", platform_url()),
        ),
    )
    parser.add_argument("--goal-id", default="", help="goal_id returned by create_task")
    parser.add_argument(
        "--task-file",
        default="",
        help="Create an isolated goal from this file, then execute (alternative to --goal-id)",
    )
    parser.add_argument("--model-id", default=os.environ.get("AGENTSWARM_MODEL_ID", ""))
    parser.add_argument("--wait-sec", type=float, default=15.0)
    parser.add_argument("--goal-timeout-sec", type=float, default=180.0)
    parser.add_argument("--owner-prefix", default="start")
    parser.add_argument(
        "--no-wait-for-workers",
        action="store_true",
        help="Skip /dispatch/capacity readiness gate",
    )
    parser.add_argument(
        "--no-realign",
        action="store_true",
        help="Skip reclaiming assignments outside this worker team",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.goal_id and not args.task_file:
        print("Provide --goal-id or --task-file", file=sys.stderr)
        return 1
    if args.goal_id and args.task_file:
        print("Use only one of --goal-id or --task-file", file=sys.stderr)
        return 1

    try:
        if args.task_file:
            goal = create_and_execute_task_file(
                args.base_url,
                args.task_file,
                model_id=args.model_id or None,
                wait_timeout_sec=args.wait_sec,
                goal_timeout_sec=args.goal_timeout_sec,
                owner_prefix=args.owner_prefix,
            )
            goal_id = str(goal.get("goal_id", ""))
        else:
            goal = execute_goal_with_volunteers(
                args.base_url,
                args.goal_id,
                model_id=args.model_id or None,
                wait_timeout_sec=args.wait_sec,
                goal_timeout_sec=args.goal_timeout_sec,
                owner_prefix=args.owner_prefix,
                wait_for_workers=not args.no_wait_for_workers,
                realign_dispatch=not args.no_realign,
            )
            goal_id = args.goal_id
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"start_task failed: {exc}", file=sys.stderr)
        return 1
    print(format_start_task_output(goal, goal_id=goal_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
