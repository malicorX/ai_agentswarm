#!/usr/bin/env python3
"""End-to-end volunteer subjective demo: goal → coordinator → creative → reviewers (P8.3)."""

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

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_agents.owner_auth import owner_auth_headers
from agentswarm_agents.volunteer_client import (
    CLIENT_VERSION,
    VolunteerClient,
    VolunteerConfig,
    resolve_reported_vram_gb,
)
from agentswarm_platform.crypto import generate_keypair, public_key_b64

DEFAULT_RUBRIC = [{"id": "quality", "weight": 1.0, "description": "Overall craft"}]
TERMINAL_GOAL_STATUSES = frozenset({"verified", "rejected"})
PRESENCE_WARMUP_SEC = 2.0
READY_TIMEOUT_SEC = 45.0


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("http"):
        raise ValueError("platform URL must start with http:// or https://")
    return clean


def _auth_headers() -> dict[str, str]:
    headers = owner_auth_headers()
    if headers:
        return headers
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip()
    if bootstrap:
        return {"X-Bootstrap-Token": bootstrap}
    return {}


def validate_demo_platform(config: dict[str, Any]) -> str:
    """Ensure staging is ready for the volunteer subjective demo."""
    if config.get("assignment_mode") != "dispatch":
        raise RuntimeError(
            f"assignment_mode must be dispatch, got {config.get('assignment_mode')!r}"
        )
    models = config.get("models")
    if isinstance(models, dict) and models.get("enforced"):
        return "llm-mock-v1"
    return "llm-mock-v1"


def register_poster_and_create_goal(
    base_url: str,
    *,
    brief: str,
    min_reviewers: int,
    pass_threshold: float,
    dispatch_include_owners: list[str] | None = None,
    timeout: float = 30.0,
) -> tuple[str, str]:
    """Register poster agent and POST /creative/goals. Returns (poster_id, goal_id)."""
    clean = _clean_url(base_url)
    headers = _auth_headers()
    if not headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN to post goals on staging"
        )

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        pub, _priv = generate_keypair()
        suffix = uuid.uuid4().hex[:8]
        reg = client.post(
            f"{clean}/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"demo-poster-{suffix}",
                "capabilities": ["codewriter"],
            },
            headers=headers,
        )
        reg.raise_for_status()
        poster_id = reg.json()["agent_id"]

        goal_payload: dict[str, object] = {
            "poster_agent_id": poster_id,
            "brief": brief,
            "rubric": DEFAULT_RUBRIC,
            "min_reviewers": min_reviewers,
            "pass_threshold": pass_threshold,
        }
        if dispatch_include_owners:
            goal_payload["dispatch_include_owners"] = dispatch_include_owners
        goal = client.post(
            f"{clean}/creative/goals",
            json=goal_payload,
            headers=headers,
        )
        goal.raise_for_status()
        goal_id = goal.json()["goal_id"]
        if not goal_id:
            raise RuntimeError("creative goal response missing goal_id")
        return poster_id, goal_id


def connect_volunteer_idle(
    base_url: str,
    *,
    capabilities: list[str],
    owner: str,
    model_id: str,
) -> tuple[VolunteerClient, VolunteerConfig]:
    suffix = uuid.uuid4().hex[:8]
    config = VolunteerConfig(
        agent_name=f"demo-{'-'.join(capabilities)}-{suffix}",
        base_url=_clean_url(base_url),
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


def run_volunteer_role(
    base_url: str,
    *,
    capabilities: list[str],
    owner: str,
    model_id: str,
    wait_timeout_sec: float,
    total_wait_sec: float | None = None,
) -> bool:
    volunteer, config = connect_volunteer_idle(
        base_url,
        capabilities=capabilities,
        owner=owner,
        model_id=model_id,
    )
    resolved_total = total_wait_sec if total_wait_sec is not None else wait_timeout_sec
    return wait_for_volunteer_assignment(
        volunteer,
        config,
        capabilities=capabilities,
        owner=owner,
        wait_timeout_sec=wait_timeout_sec,
        total_wait_sec=resolved_total,
    )


def wait_for_goal(
    base_url: str,
    goal_id: str,
    *,
    timeout_sec: float = 180.0,
    poll_sec: float = 2.0,
) -> dict[str, Any]:
    clean = _clean_url(base_url)
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


def _serve_volunteer_until(
    volunteer: VolunteerClient,
    config: VolunteerConfig,
    *,
    goal_terminal: threading.Event,
    deadline: float,
) -> None:
    while time.monotonic() < deadline and not goal_terminal.is_set():
        attempt_sec = min(config.wait_timeout_sec, deadline - time.monotonic())
        if attempt_sec <= 0:
            break
        volunteer.config = replace(config, wait_timeout_sec=attempt_sec)
        try:
            volunteer.run_once()
        except Exception:
            time.sleep(config.poll_sec)


def _build_demo_roles(
    run_id: str,
    min_reviewers: int,
) -> list[tuple[list[str], str]]:
    roles: list[tuple[list[str], str]] = [
        (["coordinator"], f"demo-coordinator-{run_id}"),
        (["creative"], f"demo-creative-{run_id}"),
    ]
    for index in range(min_reviewers):
        roles.append((["reviewer"], f"demo-reviewer-{index}-{run_id}"))
    return roles


def _start_volunteer_threads(
    base_url: str,
    *,
    roles: list[tuple[list[str], str]],
    model_id: str,
    wait_timeout_sec: float,
    goal_timeout_sec: float,
    goal_posted: threading.Event,
    goal_terminal: threading.Event | None = None,
    require_role_assignments: bool = True,
) -> tuple[list[threading.Thread], list[BaseException], threading.Barrier]:
    """Start coordinator, creative, and reviewer clients (must be idle before goal post)."""
    errors: list[BaseException] = []
    lock = threading.Lock()
    threads: list[threading.Thread] = []
    ready_barrier = threading.Barrier(len(roles) + 1, timeout=READY_TIMEOUT_SEC)

    def worker(capabilities: list[str], owner: str) -> None:
        try:
            volunteer, config = connect_volunteer_idle(
                base_url,
                capabilities=capabilities,
                owner=owner,
                model_id=model_id,
            )
            ready_barrier.wait()
            if not goal_posted.wait(timeout=goal_timeout_sec):
                raise RuntimeError("timed out waiting for creative goal to be posted")
            role_total_wait = goal_timeout_sec + (wait_timeout_sec * 4)
            deadline = time.monotonic() + role_total_wait
            if require_role_assignments:
                wait_for_volunteer_assignment(
                    volunteer,
                    config,
                    capabilities=capabilities,
                    owner=owner,
                    wait_timeout_sec=wait_timeout_sec,
                    total_wait_sec=role_total_wait,
                )
            elif goal_terminal is not None:
                _serve_volunteer_until(
                    volunteer,
                    config,
                    goal_terminal=goal_terminal,
                    deadline=deadline,
                )
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

    return threads, errors, ready_barrier


def _join_volunteer_threads(
    threads: list[threading.Thread],
    errors: list[BaseException],
    *,
    goal_timeout_sec: float,
    wait_timeout_sec: float,
) -> None:
    join_deadline = time.monotonic() + goal_timeout_sec + (wait_timeout_sec * 4) + 30.0
    for thread in threads:
        remaining = max(0.0, join_deadline - time.monotonic())
        thread.join(timeout=remaining)
    if errors:
        raise errors[0]
    alive = [thread.name for thread in threads if thread.is_alive()]
    if alive:
        raise RuntimeError(
            f"volunteer threads did not finish in time: {', '.join(alive)}"
        )


def run_volunteer_subjective_demo(
    base_url: str,
    *,
    min_reviewers: int = 3,
    pass_threshold: float = 6.0,
    model_id: str | None = None,
    use_ollama: bool = False,
    wait_timeout_sec: float = 60.0,
    goal_timeout_sec: float = 180.0,
    brief: str = "Write a haiku about volunteer AI compute on the swarm",
    require_role_assignments: bool = True,
    isolate_dispatch: bool = False,
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
    if use_ollama:
        from agentswarm_agents.ollama_executor import ollama_available
        from agentswarm_agents.model_allowlist import get_model_entry

        resolved_model = model_id or "ollama/llama3.2"
        entry = get_model_entry(resolved_model)
        if entry is None:
            raise RuntimeError(f"unknown model_id {resolved_model!r}")
        endpoint = str(entry.get("endpoint", "http://127.0.0.1:11434"))
        if not ollama_available(endpoint):
            raise RuntimeError(
                f"Ollama not reachable at {endpoint}; start Ollama or omit --ollama"
            )

    run_id = uuid.uuid4().hex[:8]
    roles = _build_demo_roles(run_id, min_reviewers)
    dispatch_include_owners = (
        [owner for _caps, owner in roles] if isolate_dispatch else None
    )

    goal_posted = threading.Event()
    goal_terminal = threading.Event()
    threads, errors, ready_barrier = _start_volunteer_threads(
        clean,
        roles=roles,
        model_id=resolved_model,
        wait_timeout_sec=wait_timeout_sec,
        goal_timeout_sec=goal_timeout_sec,
        goal_posted=goal_posted,
        goal_terminal=None if require_role_assignments else goal_terminal,
        require_role_assignments=require_role_assignments,
    )
    try:
        ready_barrier.wait()
    except threading.BrokenBarrierError as exc:
        raise RuntimeError("volunteer clients did not all register presence in time") from exc

    poster_id, goal_id = register_poster_and_create_goal(
        clean,
        brief=brief,
        min_reviewers=min_reviewers,
        pass_threshold=pass_threshold,
        dispatch_include_owners=dispatch_include_owners,
    )
    goal_posted.set()

    goal: dict[str, Any] | None = None
    goal_wait_error: list[BaseException] = []

    def _wait_goal_parallel() -> None:
        nonlocal goal
        try:
            goal = wait_for_goal(clean, goal_id, timeout_sec=goal_timeout_sec)
        except BaseException as exc:
            goal_wait_error.append(exc)
        finally:
            goal_terminal.set()

    goal_waiter = threading.Thread(target=_wait_goal_parallel, name="goal-waiter", daemon=True)
    goal_waiter.start()
    _join_volunteer_threads(
        threads,
        errors,
        goal_timeout_sec=goal_timeout_sec,
        wait_timeout_sec=wait_timeout_sec,
    )
    goal_waiter.join()
    if goal_wait_error:
        raise goal_wait_error[0]
    if goal is None:
        raise RuntimeError("goal waiter did not return a result")

    if goal.get("status") != "verified":
        raise RuntimeError(f"expected goal verified, got {goal.get('status')!r}")

    return {
        "platform_url": clean,
        "poster_agent_id": poster_id,
        "goal_id": goal_id,
        "goal_status": goal["status"],
        "aggregate_score": goal.get("aggregate_score"),
        "model_id": resolved_model,
        "min_reviewers": min_reviewers,
        "isolate_dispatch": isolate_dispatch,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run volunteer subjective path demo (coordinator → creative → reviewers)."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        ),
    )
    parser.add_argument("--min-reviewers", type=int, default=3)
    parser.add_argument("--pass-threshold", type=float, default=6.0)
    parser.add_argument("--model-id", default="")
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Use ollama/llama3.2 (requires local Ollama)",
    )
    parser.add_argument("--wait-sec", type=float, default=60.0)
    parser.add_argument("--goal-timeout-sec", type=float, default=180.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_volunteer_subjective_demo(
            args.base_url,
            min_reviewers=args.min_reviewers,
            pass_threshold=args.pass_threshold,
            model_id=args.model_id or None,
            use_ollama=args.ollama,
            wait_timeout_sec=args.wait_sec,
            goal_timeout_sec=args.goal_timeout_sec,
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Volunteer subjective demo failed: {exc}", file=sys.stderr)
        return 1
    print(f"Volunteer subjective demo OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
