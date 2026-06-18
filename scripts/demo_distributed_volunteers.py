#!/usr/bin/env python3
"""Distributed volunteer subjective demo across SSH hosts (e.g. sparky1, sparky2, local)."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from demo_volunteer_subjective import (  # noqa: E402
    READY_TIMEOUT_SEC,
    _build_demo_roles,
    connect_volunteer_idle,
    register_poster_and_create_goal,
    validate_demo_platform,
    wait_for_goal,
    wait_for_volunteer_assignment,
)

@dataclass(frozen=True)
class RoleHost:
    host: str | None  # None = run on orchestrator machine
    capabilities: list[str]
    owner: str


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("http"):
        raise ValueError("platform URL must start with http:// or https://")
    return clean


def _ssh(host: str, remote_command: str, *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", host, remote_command],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _default_role_hosts(run_id: str, min_reviewers: int) -> list[RoleHost]:
    sparky1 = os.environ.get("AGENTSWARM_SPARKY1_HOST", "sparky1").strip()
    sparky2 = os.environ.get("AGENTSWARM_SPARKY2_HOST", "sparky2").strip()
    roles = _build_demo_roles(run_id, min_reviewers)
    if len(roles) != 2 + min_reviewers:
        raise RuntimeError(f"unexpected role count from demo builder: {len(roles)}")

    # Default 3-host layout when min_reviewers=1:
    # sparky1=coordinator, sparky2=creative, local=reviewer-0.
    if min_reviewers == 1 and len(roles) == 3:
        coordinator_caps, coordinator_owner = roles[0]
        creative_caps, creative_owner = roles[1]
        reviewer_caps, reviewer_owner = roles[2]
        return [
            RoleHost(sparky1, coordinator_caps, coordinator_owner),
            RoleHost(sparky2, creative_caps, creative_owner),
            RoleHost(None, reviewer_caps, reviewer_owner),
        ]

    # Fallback: first role on sparky1, second on sparky2, rest local.
    hosts: list[RoleHost] = []
    remote_hosts = [sparky1, sparky2]
    for index, (caps, owner) in enumerate(roles):
        if index < len(remote_hosts):
            hosts.append(RoleHost(remote_hosts[index], caps, owner))
        else:
            hosts.append(RoleHost(None, caps, owner))
    return hosts


def _remote_repo_path(host: str) -> str:
    override = os.environ.get("AGENTSWARM_DIST_REPO", "").strip()
    if override:
        return override
    return "~/ai_agentSwarm"


def _role_slug(capabilities: list[str], owner: str) -> str:
    return f"{'-'.join(capabilities)}-{owner}"


def _push_remote_env(host: str, run_id: str, env: dict[str, str]) -> str:
    remote_path = f"/tmp/agentswarm-env-{run_id}"
    clean_env = {key: value.replace("\r", "").strip() for key, value in env.items()}
    payload = "\n".join(f"{key}={value}" for key, value in clean_env.items()) + "\n"
    result = _ssh(host, f"cat > {shlex.quote(remote_path)}", input_text=payload)
    if result.returncode != 0:
        raise RuntimeError(
            f"failed to write env on {host}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return remote_path


def _start_remote_worker(
    host: str,
    role: RoleHost,
    *,
    run_id: str,
    base_url: str,
    model_id: str,
    wait_sec: float,
    total_wait_sec: float,
    env_path: str,
) -> tuple[str, str, str]:
    repo = _remote_repo_path(host)
    slug = _role_slug(role.capabilities, role.owner)
    go_file = f"/tmp/agentswarm-go-{run_id}-{slug}"
    pid_file = f"/tmp/agentswarm-pid-{run_id}-{slug}"
    log_file = f"/tmp/agentswarm-log-{run_id}-{slug}"
    caps = ",".join(role.capabilities)
    go_timeout_sec = max(total_wait_sec + 180.0, 300.0)
    remote_cmd = (
        f"set -euo pipefail; "
        f"cd {repo}; "
        f"export AGENTSWARM_REPO_ROOT=\"$(pwd)\"; "
        f"test -x .venv/bin/python || {{ echo 'missing venv at {repo}/.venv'; exit 2; }}; "
        f"set -a; source {shlex.quote(env_path)}; set +a; "
        f"export AGENTSWARM_BOOTSTRAP_TOKEN=\"$(printf %s \"$AGENTSWARM_BOOTSTRAP_TOKEN\" | tr -d '\\r')\"; "
        f"export AGENTSWARM_ASSIGNMENT_SECRET=\"$(printf %s \"$AGENTSWARM_ASSIGNMENT_SECRET\" | tr -d '\\r')\"; "
        f"nohup .venv/bin/python scripts/run_volunteer_role.py "
        f"--base-url {shlex.quote(base_url)} "
        f"--capabilities {shlex.quote(caps)} "
        f"--owner {shlex.quote(role.owner)} "
        f"--model-id {shlex.quote(model_id)} "
        f"--wait-sec {wait_sec} "
        f"--total-wait-sec {total_wait_sec} "
        f"--go-file {shlex.quote(go_file)} "
        f"--go-timeout-sec {go_timeout_sec} "
        f"> {shlex.quote(log_file)} 2>&1 & "
        f"echo $! > {shlex.quote(pid_file)}; "
        f"echo started"
    )
    result = _ssh(host, remote_cmd)
    if result.returncode != 0:
        raise RuntimeError(
            f"failed to start worker on {host} ({slug}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return go_file, pid_file, log_file


def _wait_remote_ready(host: str, log_file: str, timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        result = _ssh(host, f"grep -q '^READY$' {shlex.quote(log_file)} 2>/dev/null && echo ok || true")
        if result.returncode == 0 and result.stdout.strip() == "ok":
            return
        time.sleep(1.0)
    tail = _ssh(host, f"tail -n 20 {shlex.quote(log_file)} 2>/dev/null || true")
    detail = tail.stdout.strip() or tail.stderr.strip() or "(no log output)"
    raise RuntimeError(f"remote worker on {host} did not become READY in {timeout_sec}s:\n{detail}")


def _signal_remote_go(host: str, go_file: str) -> None:
    result = _ssh(host, f"touch {shlex.quote(go_file)}")
    if result.returncode != 0:
        raise RuntimeError(f"failed to signal go on {host}: {result.stderr.strip()}")


def _tail_remote_log(host: str, log_file: str, *, lines: int = 30) -> str:
    result = _ssh(host, f"tail -n {lines} {shlex.quote(log_file)} 2>/dev/null || true")
    return result.stdout.strip() or result.stderr.strip() or "(no log output)"


def _stop_remote_worker(host: str, pid_file: str, go_file: str, log_file: str) -> None:
    _ssh(
        host,
        f"if [ -f {shlex.quote(pid_file)} ]; then kill $(cat {shlex.quote(pid_file)}) 2>/dev/null || true; fi; "
        f"rm -f {shlex.quote(pid_file)} {shlex.quote(go_file)} {shlex.quote(log_file)}",
    )


def _run_local_role(
    base_url: str,
    role: RoleHost,
    *,
    model_id: str,
    wait_sec: float,
    total_wait_sec: float,
    ready: threading.Event,
    go: threading.Event,
    errors: list[BaseException],
    lock: threading.Lock,
) -> None:
    try:
        volunteer, config = connect_volunteer_idle(
            base_url,
            capabilities=role.capabilities,
            owner=role.owner,
            model_id=model_id,
        )
        ready.set()
        if not go.wait(timeout=READY_TIMEOUT_SEC + 60.0):
            raise RuntimeError(f"local volunteer {role.owner} timed out waiting for go signal")
        wait_for_volunteer_assignment(
            volunteer,
            config,
            capabilities=role.capabilities,
            owner=role.owner,
            wait_timeout_sec=wait_sec,
            total_wait_sec=total_wait_sec,
        )
    except BaseException as exc:
        with lock:
            errors.append(exc)


def run_distributed_volunteer_demo(
    base_url: str,
    *,
    min_reviewers: int = 1,
    pass_threshold: float = 6.0,
    model_id: str | None = None,
    wait_timeout_sec: float = 60.0,
    goal_timeout_sec: float = 300.0,
    brief: str = "Write a haiku about volunteer AI compute across sparky machines",
    role_hosts: list[RoleHost] | None = None,
) -> dict[str, Any]:
    clean = _clean_url(base_url)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        config_body = config.json()

    resolved_model = model_id or validate_demo_platform(config_body)
    dispatch = config_body.get("dispatch")
    if isinstance(dispatch, dict) and dispatch.get("long_poll_max_sec"):
        max_wait = float(dispatch["long_poll_max_sec"])
        if wait_timeout_sec > max_wait:
            wait_timeout_sec = max_wait

    run_id = uuid.uuid4().hex[:8]
    hosts = role_hosts or _default_role_hosts(run_id, min_reviewers)
    owners = [role.owner for role in hosts]
    total_role_wait = goal_timeout_sec + (wait_timeout_sec * 4)

    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").replace("\r", "").strip()
    assignment_secret = os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET", "").replace("\r", "").strip()
    if not bootstrap or not assignment_secret:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN and AGENTSWARM_ASSIGNMENT_SECRET for distributed staging demo"
        )
    remote_env = {
        "AGENTSWARM_BOOTSTRAP_TOKEN": bootstrap,
        "AGENTSWARM_ASSIGNMENT_SECRET": assignment_secret,
        "AGENTSWARM_STAGING_API_URL": clean,
    }

    remote_workers: list[tuple[str, str, str, str]] = []
    remote_env_paths: dict[str, str] = {}
    try:
        for role in hosts:
            if role.host is None:
                continue
            if role.host not in remote_env_paths:
                remote_env_paths[role.host] = _push_remote_env(role.host, run_id, remote_env)
            go_file, pid_file, log_file = _start_remote_worker(
                role.host,
                role,
                run_id=run_id,
                base_url=clean,
                model_id=resolved_model,
                wait_sec=wait_timeout_sec,
                total_wait_sec=total_role_wait,
                env_path=remote_env_paths[role.host],
            )
            remote_workers.append((role.host, go_file, pid_file, log_file))

        for host, _go, _pid, log_file in remote_workers:
            _wait_remote_ready(host, log_file, READY_TIMEOUT_SEC)

        local_ready = threading.Event()
        local_go = threading.Event()
        errors: list[BaseException] = []
        lock = threading.Lock()
        local_threads: list[threading.Thread] = []
        for role in hosts:
            if role.host is not None:
                continue
            thread = threading.Thread(
                target=_run_local_role,
                kwargs={
                    "base_url": clean,
                    "role": role,
                    "model_id": resolved_model,
                    "wait_sec": wait_timeout_sec,
                    "total_wait_sec": total_role_wait,
                    "ready": local_ready,
                    "go": local_go,
                    "errors": errors,
                    "lock": lock,
                },
                name=f"local-{'-'.join(role.capabilities)}",
                daemon=True,
            )
            thread.start()
            local_threads.append(thread)

        if local_threads and not local_ready.wait(timeout=READY_TIMEOUT_SEC):
            raise RuntimeError("local volunteer did not register presence in time")

        poster_id, goal_id = register_poster_and_create_goal(
            clean,
            brief=brief,
            min_reviewers=min_reviewers,
            pass_threshold=pass_threshold,
            dispatch_include_owners=owners,
        )

        for host, go_file, _pid, _log in remote_workers:
            _signal_remote_go(host, go_file)
        local_go.set()

        goal = wait_for_goal(clean, goal_id, timeout_sec=goal_timeout_sec)
        join_deadline = time.monotonic() + total_role_wait + 30.0
        for thread in local_threads:
            thread.join(timeout=max(0.0, join_deadline - time.monotonic()))
        if errors:
            raise errors[0]

        if goal.get("status") != "verified":
            raise RuntimeError(f"expected goal verified, got {goal.get('status')!r}")

        return {
            "platform_url": clean,
            "run_id": run_id,
            "poster_agent_id": poster_id,
            "goal_id": goal_id,
            "goal_status": goal["status"],
            "aggregate_score": goal.get("aggregate_score"),
            "model_id": resolved_model,
            "min_reviewers": min_reviewers,
            "hosts": [
                {
                    "host": role.host or "local",
                    "capabilities": role.capabilities,
                    "owner": role.owner,
                }
                for role in hosts
            ],
        }
    finally:
        for host, go_file, pid_file, log_file in remote_workers:
            _stop_remote_worker(host, pid_file, go_file, log_file)
        for host, env_path in remote_env_paths.items():
            _ssh(host, f"rm -f {shlex.quote(env_path)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Distributed volunteer subjective demo (SSH workers + local coordinator/reviewer)."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        ),
    )
    parser.add_argument("--min-reviewers", type=int, default=1)
    parser.add_argument("--pass-threshold", type=float, default=6.0)
    parser.add_argument("--model-id", default="")
    parser.add_argument("--wait-sec", type=float, default=60.0)
    parser.add_argument("--goal-timeout-sec", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_distributed_volunteer_demo(
            args.base_url,
            min_reviewers=args.min_reviewers,
            pass_threshold=args.pass_threshold,
            model_id=args.model_id or None,
            wait_timeout_sec=args.wait_sec,
            goal_timeout_sec=args.goal_timeout_sec,
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Distributed volunteer demo failed: {exc}", file=sys.stderr)
        return 1
    print(f"Distributed volunteer demo OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
