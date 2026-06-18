"""Engineering goal posting and orchestrated volunteer execution."""

from __future__ import annotations

import threading
import uuid
from typing import Any

import httpx

from agentswarm_agents.engineering_lab import (
    default_verification_spec,
    get_fixture_spec,
    list_fixtures,
    reset_fixture,
)
from agentswarm_agents.volunteer_team import (
    clean_platform_url,
    goal_auth_headers,
    join_volunteer_threads,
    start_volunteer_threads,
    validate_dispatch_platform,
    wait_for_goal,
)
from agentswarm_platform.crypto import generate_keypair, public_key_b64

ENGINEERING_ROLE_NAMES = ("coordinator", "codewriter", "builder", "tester", "reviewer")


def build_engineering_roles(
    run_id: str,
    *,
    owner_prefix: str = "solve",
    sandbox_tester: bool = False,
    sandbox_builder: bool = False,
    windows_sandbox_tester: bool = False,
    windows_sandbox_builder: bool = False,
) -> list[tuple[list[str], str]]:
    roles: list[tuple[list[str], str]] = []
    for role in ENGINEERING_ROLE_NAMES:
        if role == "builder" and not (sandbox_builder or windows_sandbox_builder):
            continue
        if role == "tester" and windows_sandbox_tester:
            capabilities = ["sandbox.windows.test"]
        elif role == "tester" and sandbox_tester:
            capabilities = ["sandbox.test"]
        elif role == "builder" and windows_sandbox_builder:
            capabilities = ["sandbox.windows.build"]
        elif role == "builder" and sandbox_builder:
            capabilities = ["sandbox.build"]
        else:
            capabilities = [role]
        roles.append((capabilities, f"{owner_prefix}-{role}-{run_id}"))
    return roles


def register_poster_and_create_engineering_goal(
    base_url: str,
    *,
    brief: str,
    verification_spec: dict[str, str] | None = None,
    workspace: dict[str, str] | None = None,
    dispatch_include_owners: list[str] | None = None,
    timeout: float = 30.0,
) -> tuple[str, str]:
    clean = clean_platform_url(base_url)
    headers = goal_auth_headers()
    if not headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN to post engineering goals"
        )
    spec = verification_spec or default_verification_spec()
    get_fixture_spec(spec["fixture"])

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        pub, _priv = generate_keypair()
        suffix = uuid.uuid4().hex[:8]
        reg = client.post(
            f"{clean}/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"solve-poster-{suffix}",
                "capabilities": ["codewriter"],
            },
            headers=headers,
        )
        reg.raise_for_status()
        poster_id = reg.json()["agent_id"]

        goal_payload: dict[str, object] = {
            "poster_agent_id": poster_id,
            "brief": brief,
            "rubric": [],
            "goal_kind": "engineering",
            "verification_spec": spec,
            "min_reviewers": 1,
        }
        if dispatch_include_owners:
            goal_payload["dispatch_include_owners"] = dispatch_include_owners
        if workspace:
            goal_payload["workspace"] = workspace
        goal = client.post(f"{clean}/creative/goals", json=goal_payload, headers=headers)
        goal.raise_for_status()
        goal_id = goal.json()["goal_id"]
        if not goal_id:
            raise RuntimeError("engineering goal response missing goal_id")
        return poster_id, goal_id


def solve_engineering_goal(
    base_url: str,
    brief: str,
    *,
    fixture: str = "primes",
    model_id: str | None = None,
    wait_timeout_sec: float = 60.0,
    goal_timeout_sec: float = 300.0,
    isolate_dispatch: bool = True,
    owner_prefix: str = "solve",
) -> dict[str, Any]:
    """Post an engineering goal and run the full volunteer team until verified."""
    clean = clean_platform_url(base_url)
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

    run_id = uuid.uuid4().hex[:8]
    roles = build_engineering_roles(run_id, owner_prefix=owner_prefix)
    dispatch_include_owners = (
        [owner for _caps, owner in roles] if isolate_dispatch else None
    )
    spec = default_verification_spec(fixture)
    reset_fixture(fixture)

    goal_posted = threading.Event()
    stop_volunteers = threading.Event()
    threads, errors, ready_barrier, agent_credentials = start_volunteer_threads(
        clean,
        roles=roles,
        model_id=resolved_model,
        wait_timeout_sec=wait_timeout_sec,
        goal_timeout_sec=goal_timeout_sec,
        goal_posted=goal_posted,
        require_role_assignments=True,
        agent_name_prefix=owner_prefix,
        stop=stop_volunteers,
    )
    succeeded = False
    try:
        try:
            ready_barrier.wait()
        except threading.BrokenBarrierError as exc:
            raise RuntimeError("volunteer team did not register on the platform in time") from exc

        poster_id, goal_id = register_poster_and_create_engineering_goal(
            clean,
            brief=brief,
            verification_spec=spec,
            dispatch_include_owners=dispatch_include_owners,
        )
        goal_posted.set()

        goal = wait_for_goal(clean, goal_id, timeout_sec=goal_timeout_sec)

        if goal.get("status") != "verified":
            raise RuntimeError(f"goal not verified (status={goal.get('status')!r})")

        succeeded = True
        return {
            "platform_url": clean,
            "poster_agent_id": poster_id,
            "goal_id": goal_id,
            "goal_status": goal["status"],
            "goal_kind": goal.get("goal_kind", "engineering"),
            "brief": brief,
            "verification_spec": spec,
            "artifact_text": goal.get("artifact_text"),
            "model_id": resolved_model,
            "roles": [
                {"capabilities": caps, "owner": owner} for caps, owner in roles
            ],
            "_agent_credentials": agent_credentials,
        }
    finally:
        stop_volunteers.set()
        join_volunteer_threads(
            threads,
            errors,
            goal_timeout_sec=goal_timeout_sec,
            wait_timeout_sec=wait_timeout_sec,
            join_timeout_sec=(
                goal_timeout_sec + (wait_timeout_sec * 4) + 30.0
                if succeeded
                else min(wait_timeout_sec * 2, 45.0)
            ),
            raise_errors=succeeded,
        )


__all__ = [
    "ENGINEERING_ROLE_NAMES",
    "build_engineering_roles",
    "list_fixtures",
    "register_poster_and_create_engineering_goal",
    "solve_engineering_goal",
]
