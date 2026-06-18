"""Shared helpers for multi-volunteer goal demos and the solve CLI."""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import replace
from collections.abc import Callable
from typing import Any

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers
from agentswarm_agents.volunteer_client import (
    CLIENT_VERSION,
    VolunteerClient,
    VolunteerConfig,
    resolve_reported_vram_gb,
)

TERMINAL_GOAL_STATUSES = frozenset({"verified", "rejected"})
READY_TIMEOUT_SEC = 45.0


def clean_platform_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("http"):
        raise ValueError("platform URL must start with http:// or https://")
    return clean


def goal_auth_headers() -> dict[str, str]:
    headers = owner_auth_headers()
    if headers:
        return headers
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip().replace("\r", "")
    if bootstrap:
        return {"X-Bootstrap-Token": bootstrap}
    return {}


def validate_dispatch_platform(config: dict[str, Any]) -> str:
    if config.get("assignment_mode") != "dispatch":
        raise RuntimeError(
            f"assignment_mode must be dispatch, got {config.get('assignment_mode')!r}"
        )
    models = config.get("models")
    if isinstance(models, dict) and models.get("enforced"):
        return "llm-mock-v1"
    return "llm-mock-v1"


def connect_volunteer_idle(
    base_url: str,
    *,
    capabilities: list[str],
    owner: str,
    model_id: str,
    agent_name_prefix: str = "solve",
) -> tuple[VolunteerClient, VolunteerConfig]:
    suffix = uuid.uuid4().hex[:8]
    config = VolunteerConfig(
        agent_name=f"{agent_name_prefix}-{'-'.join(capabilities)}-{suffix}",
        base_url=clean_platform_url(base_url),
        owner=owner,
        capabilities=capabilities,
        model_id=model_id,
        wait_timeout_sec=60.0,
        poll_sec=1.0,
    )
    volunteer = VolunteerClient(config)
    volunteer.connect()
    client = volunteer._client
    if client is None:
        raise RuntimeError("volunteer connect did not initialize dispatch client")
    client.heartbeat(
        config.capabilities,
        status="idle",
        model_id=config.model_id,
        client_version=CLIENT_VERSION,
        ttl_sec=config.heartbeat_ttl_sec,
        vram_gb=resolve_reported_vram_gb(config),
    )
    return volunteer, config


def wait_for_volunteer_assignment(
    volunteer: VolunteerClient,
    config: VolunteerConfig,
    *,
    capabilities: list[str],
    owner: str,
    wait_timeout_sec: float,
    total_wait_sec: float,
) -> bool:
    deadline = time.monotonic() + total_wait_sec
    while time.monotonic() < deadline:
        attempt_sec = min(wait_timeout_sec, deadline - time.monotonic())
        if attempt_sec <= 0:
            break
        volunteer.config = replace(config, wait_timeout_sec=attempt_sec)
        if volunteer.run_once():
            return True
    raise RuntimeError(
        f"volunteer {capabilities} ({owner}) timed out waiting for an assignment"
    )


def wait_for_goal(
    base_url: str,
    goal_id: str,
    *,
    timeout_sec: float = 300.0,
    poll_sec: float = 2.0,
) -> dict[str, Any]:
    clean = clean_platform_url(base_url)
    deadline = time.monotonic() + timeout_sec
    last_status = "unknown"
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        while time.monotonic() < deadline:
            response = client.get(f"{clean}/creative/goals/{goal_id}")
            response.raise_for_status()
            body = response.json()
            last_status = str(body.get("status", "unknown"))
            if last_status in TERMINAL_GOAL_STATUSES:
                return body
            time.sleep(poll_sec)
    raise RuntimeError(
        f"goal {goal_id} did not reach terminal status within {timeout_sec}s (last={last_status})"
    )


def start_volunteer_threads(
    base_url: str,
    *,
    roles: list[tuple[list[str], str]],
    model_id: str,
    wait_timeout_sec: float,
    goal_timeout_sec: float,
    goal_posted: threading.Event,
    require_role_assignments: bool = True,
    agent_name_prefix: str = "solve",
    stop: threading.Event | None = None,
) -> tuple[list[threading.Thread], list[BaseException], threading.Barrier, dict[str, tuple[str, bytes]]]:
    errors: list[BaseException] = []
    lock = threading.Lock()
    threads: list[threading.Thread] = []
    ready_barrier = threading.Barrier(len(roles) + 1, timeout=READY_TIMEOUT_SEC)
    agent_credentials: dict[str, tuple[str, bytes]] = {}
    shared_stop = stop if stop is not None else threading.Event()

    def worker(capabilities: list[str], owner: str) -> None:
        try:
            volunteer, config = connect_volunteer_idle(
                base_url,
                capabilities=capabilities,
                owner=owner,
                model_id=model_id,
                agent_name_prefix=agent_name_prefix,
            )
            client = volunteer._client
            if client is not None:
                with lock:
                    agent_credentials[owner] = (client.agent_id, client.private_key)
            ready_barrier.wait()
            if shared_stop.is_set():
                return
            if not goal_posted.wait(timeout=goal_timeout_sec):
                raise RuntimeError("timed out waiting for goal to be posted")
            role_total_wait = goal_timeout_sec + (wait_timeout_sec * 4)
            deadline = time.monotonic() + role_total_wait
            while not shared_stop.is_set() and time.monotonic() < deadline:
                volunteer.config = replace(
                    config, wait_timeout_sec=min(wait_timeout_sec, 15.0)
                )
                if volunteer.run_once():
                    return
        except BaseException as exc:
            with lock:
                errors.append(exc)

    for capabilities, owner in roles:
        thread = threading.Thread(
            target=worker,
            args=(capabilities, owner),
            name=f"volunteer-{'-'.join(capabilities)}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    return threads, errors, ready_barrier, agent_credentials


def join_volunteer_threads(
    threads: list[threading.Thread],
    errors: list[BaseException],
    *,
    goal_timeout_sec: float,
    wait_timeout_sec: float,
    join_timeout_sec: float | None = None,
    raise_errors: bool = True,
) -> None:
    if join_timeout_sec is None:
        join_timeout_sec = goal_timeout_sec + (wait_timeout_sec * 4) + 30.0
    join_deadline = time.monotonic() + join_timeout_sec
    for thread in threads:
        remaining = max(0.0, join_deadline - time.monotonic())
        thread.join(timeout=remaining)
    if raise_errors and errors:
        raise errors[0]
    alive = [thread.name for thread in threads if thread.is_alive()]
    if raise_errors and alive:
        raise RuntimeError(f"volunteer threads did not finish in time: {', '.join(alive)}")


def run_volunteer_workers_until_stopped(
    base_url: str,
    *,
    roles: list[tuple[list[str], str]],
    model_id: str,
    wait_timeout_sec: float,
    stop: threading.Event,
    on_log: Callable[[str], None] | None = None,
) -> None:
    """Keep volunteer workers idle and execute assignments until stop is set."""

    def log(message: str) -> None:
        if on_log is not None:
            on_log(message)
        else:
            print(message, flush=True)

    def worker(capabilities: list[str], owner: str) -> None:
        try:
            volunteer, config = connect_volunteer_idle(
                base_url,
                capabilities=capabilities,
                owner=owner,
                model_id=model_id,
            )
            log(f"ready {owner} ({', '.join(capabilities)})")
            while not stop.is_set():
                volunteer.config = replace(config, wait_timeout_sec=wait_timeout_sec)
                try:
                    if volunteer.run_once():
                        log(f"completed assignment for {owner}")
                except Exception as exc:
                    log(f"error {owner}: {exc}")
                    stop.wait(2.0)
        except Exception as exc:
            log(f"fatal {owner}: {exc}")

    threads = [
        threading.Thread(
            target=worker,
            args=(capabilities, owner),
            name=f"work-{'-'.join(capabilities)}",
            daemon=True,
        )
        for capabilities, owner in roles
    ]
    for thread in threads:
        thread.start()
    while not stop.is_set():
        stop.wait(1.0)
