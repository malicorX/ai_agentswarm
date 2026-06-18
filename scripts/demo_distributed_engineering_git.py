#!/usr/bin/env python3
"""Distributed git engineering: sparky1=coordinator+tester, sparky2=codewriter, local=reviewer."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from demo_distributed_volunteers import (  # noqa: E402
    READY_TIMEOUT_SEC,
    RoleHost,
    _clean_url,
    _push_remote_env,
    _signal_remote_go,
    _ssh,
    _start_remote_worker,
    _stop_remote_worker,
    _tail_remote_log,
    _wait_remote_ready,
)
from demo_engineering_goal import _build_engineering_roles  # noqa: E402
from demo_volunteer_subjective import validate_demo_platform, wait_for_goal  # noqa: E402
from agentswarm_agents.engineering_goal import (  # noqa: E402
    build_engineering_roles,
    register_poster_and_create_engineering_goal,
)
from agentswarm_agents.engineering_lab import default_verification_spec  # noqa: E402
from agentswarm_agents.engineering_workspace import resolve_engineering_git_workspace  # noqa: E402


def _default_git_role_hosts(run_id: str) -> list[RoleHost]:
    """Codewriter on sparky2; tester on sparky1 — proves git handoff across hosts."""
    sparky1 = os.environ.get("AGENTSWARM_SPARKY1_HOST", "sparky1").strip()
    sparky2 = os.environ.get("AGENTSWARM_SPARKY2_HOST", "sparky2").strip()
    roles = _build_engineering_roles(run_id)
    role_by_name = {caps[0]: (caps, owner) for caps, owner in roles}
    layout = [
        ("coordinator", sparky1),
        ("codewriter", sparky2),
        ("tester", sparky1),
        ("reviewer", None),
    ]
    hosts: list[RoleHost] = []
    for role_name, host in layout:
        caps, owner = role_by_name[role_name]
        hosts.append(RoleHost(host, caps, owner))
    return hosts


def _sandbox_git_in_container_role_hosts(run_id: str) -> list[RoleHost]:
    """D6 layout: codewriter git on sparky2; sandbox tester on sparky1."""
    sparky1 = os.environ.get("AGENTSWARM_SPARKY1_HOST", "sparky1").strip()
    sparky2 = os.environ.get("AGENTSWARM_SPARKY2_HOST", "sparky2").strip()
    roles = build_engineering_roles(
        run_id,
        owner_prefix="dist-git",
        sandbox_tester=True,
    )
    role_by_cap = {caps[0]: (caps, owner) for caps, owner in roles}
    layout: list[tuple[str, str | None]] = [
        ("coordinator", sparky1),
        ("codewriter", sparky2),
        ("sandbox.test", sparky1),
        ("reviewer", None),
    ]
    hosts: list[RoleHost] = []
    for cap, host in layout:
        caps, owner = role_by_cap[cap]
        hosts.append(RoleHost(host, caps, owner))
    return hosts


def _git_verification_spec(fixture: str = "primes", *, git_in_container: bool = False) -> dict[str, str]:
    spec = default_verification_spec(fixture)
    spec["workspace_mode"] = "git"
    if git_in_container:
        spec["git_in_container"] = "true"
    return spec


def _forge_audit_flags(client: httpx.Client, base_url: str, goal_id: str) -> dict[str, bool]:
    resp = client.get(f"{base_url}/audit", params={"limit": 200})
    resp.raise_for_status()
    events = resp.json()
    minted = False
    installed = False
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") not in ("forge.mint", "forge.install"):
            continue
        details = event.get("details")
        if not isinstance(details, dict) or details.get("goal_id") != goal_id:
            continue
        if event.get("event_type") == "forge.mint":
            minted = True
        if event.get("event_type") == "forge.install":
            installed = True
    return {"forge_minted": minted, "forge_auto_installed": installed}


def run_distributed_engineering_git_demo(
    base_url: str,
    *,
    model_id: str | None = None,
    wait_timeout_sec: float = 60.0,
    goal_timeout_sec: float = 300.0,
    brief: str = "Implement a Python program that prints the first 100 primes, one per line",
    fixture: str = "primes",
    workspace_repo_url: str | None = None,
    git_in_container: bool = False,
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

    workspace = resolve_engineering_git_workspace(
        fixture=fixture,
        workspace_repo_url=workspace_repo_url,
    )
    if workspace["repo_url"].startswith("file:"):
        raise RuntimeError(
            "distributed git demo requires a network git URL; "
            "set AGENTSWARM_GIT_REPO_URL or run .\\scripts\\init_git_workspace_staging.ps1"
        )

    run_id = uuid.uuid4().hex[:8]
    spec = _git_verification_spec(fixture, git_in_container=git_in_container)
    hosts = (
        _sandbox_git_in_container_role_hosts(run_id)
        if git_in_container
        else _default_git_role_hosts(run_id)
    )
    owners = [role.owner for role in hosts]
    total_role_wait = goal_timeout_sec + (wait_timeout_sec * 6)

    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").replace("\r", "").strip()
    assignment_secret = os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET", "").replace("\r", "").strip()
    if not bootstrap or not assignment_secret:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN and AGENTSWARM_ASSIGNMENT_SECRET for distributed demo"
        )
    remote_env = {
        "AGENTSWARM_BOOTSTRAP_TOKEN": bootstrap,
        "AGENTSWARM_ASSIGNMENT_SECRET": assignment_secret,
        "AGENTSWARM_STAGING_API_URL": clean,
        "AGENTSWARM_GIT_REPO_URL": workspace["repo_url"],
    }
    if git_in_container:
        remote_env.setdefault(
            "AGENTSWARM_SANDBOX_MOCK",
            os.environ.get("AGENTSWARM_SANDBOX_MOCK", "1"),
        )

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

        local_ready = threading.Barrier(
            sum(1 for role in hosts if role.host is None) + 1,
            timeout=READY_TIMEOUT_SEC,
        )
        local_go = threading.Event()
        errors: list[BaseException] = []
        lock = threading.Lock()
        local_threads: list[threading.Thread] = []

        def _local_worker(role: RoleHost) -> None:
            try:
                from dataclasses import replace

                from demo_volunteer_subjective import connect_volunteer_idle

                volunteer, config = connect_volunteer_idle(
                    clean,
                    capabilities=role.capabilities,
                    owner=role.owner,
                    model_id=resolved_model,
                )
                local_ready.wait()
                if not local_go.wait(timeout=READY_TIMEOUT_SEC + 60.0):
                    raise RuntimeError(
                        f"local volunteer {role.owner} timed out waiting for go signal"
                    )
                deadline = time.monotonic() + total_role_wait
                while time.monotonic() < deadline:
                    volunteer.config = replace(
                        config, wait_timeout_sec=min(wait_timeout_sec, 15.0)
                    )
                    if volunteer.run_once():
                        return
                raise RuntimeError(
                    f"local volunteer {role.owner} did not complete within {total_role_wait}s"
                )
            except BaseException as exc:
                with lock:
                    errors.append(exc)

        for role in hosts:
            if role.host is not None:
                continue
            thread = threading.Thread(
                target=_local_worker,
                args=(role,),
                name=f"local-{'-'.join(role.capabilities)}",
                daemon=True,
            )
            thread.start()
            local_threads.append(thread)

        try:
            local_ready.wait()
        except threading.BrokenBarrierError as exc:
            raise RuntimeError("local volunteers did not all register in time") from exc

        poster_id, goal_id = register_poster_and_create_engineering_goal(
            clean,
            brief=brief,
            verification_spec=spec,
            workspace=workspace,
            dispatch_include_owners=owners,
        )

        for host, go_file, _pid, _log in remote_workers:
            _signal_remote_go(host, go_file)
        local_go.set()

        try:
            goal = wait_for_goal(clean, goal_id, timeout_sec=goal_timeout_sec)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}\nRemote worker logs:\n"
                + "\n---\n".join(
                    f"{host}:\n{_tail_remote_log(host, log)}"
                    for host, _go, _pid, log in remote_workers
                )
            ) from exc
        join_deadline = time.monotonic() + total_role_wait + 30.0
        for thread in local_threads:
            thread.join(timeout=max(0.0, join_deadline - time.monotonic()))
        if errors:
            raise errors[0]

        if goal.get("status") != "verified":
            raise RuntimeError(f"expected goal verified, got {goal.get('status')!r}")

        with httpx.Client(timeout=30.0, follow_redirects=True) as audit_client:
            forge_flags = _forge_audit_flags(audit_client, clean, goal_id)

        return {
            "platform_url": clean,
            "run_id": run_id,
            "poster_agent_id": poster_id,
            "goal_id": goal_id,
            "goal_status": goal["status"],
            "goal_kind": goal.get("goal_kind", "engineering"),
            "verification_spec": spec,
            "workspace": workspace,
            "workspace_ref": goal.get("workspace_ref"),
            "forge_minted": forge_flags["forge_minted"],
            "forge_auto_installed": forge_flags["forge_auto_installed"],
            "model_id": resolved_model,
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
            _ssh(host, f"rm -f {env_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Distributed git engineering goal demo.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        ),
    )
    parser.add_argument("--model-id", default="")
    parser.add_argument("--wait-sec", type=float, default=60.0)
    parser.add_argument("--goal-timeout-sec", type=float, default=300.0)
    parser.add_argument("--fixture", default="primes")
    parser.add_argument(
        "--workspace-repo-url",
        default=os.environ.get("AGENTSWARM_GIT_REPO_URL", ""),
        help="SSH git URL for shared bare repo (default: AGENTSWARM_GIT_REPO_URL)",
    )
    parser.add_argument(
        "--git-in-container",
        action="store_true",
        help="D6: sandbox.test with git clone inside container on sparky1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_url = args.workspace_repo_url.strip() or None
    try:
        result = run_distributed_engineering_git_demo(
            args.base_url,
            model_id=args.model_id or None,
            wait_timeout_sec=args.wait_sec,
            goal_timeout_sec=args.goal_timeout_sec,
            fixture=args.fixture,
            workspace_repo_url=repo_url,
            git_in_container=args.git_in_container,
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Distributed git engineering demo failed: {exc}", file=sys.stderr)
        return 1
    print(f"Distributed git engineering demo OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
