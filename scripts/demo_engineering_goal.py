#!/usr/bin/env python3
"""End-to-end engineering goal demo: coordinator → codewriter → tester → reviewer."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_agents.engineering_goal import (  # noqa: E402
    build_engineering_roles,
    register_poster_and_create_engineering_goal,
    solve_engineering_goal,
)


def _build_engineering_roles(run_id: str) -> list[tuple[list[str], str]]:
    return build_engineering_roles(run_id, owner_prefix="demo")


def run_engineering_goal_demo(
    base_url: str,
    *,
    model_id: str | None = None,
    wait_timeout_sec: float = 60.0,
    goal_timeout_sec: float = 300.0,
    brief: str = "Implement a Python program that prints the first 100 primes, one per line",
    verification_spec: dict[str, str] | None = None,
    isolate_dispatch: bool = True,
    owner_prefix: str | None = None,
) -> dict[str, Any]:
    fixture = (
        verification_spec.get("fixture", "primes")
        if verification_spec
        else "primes"
    )
    resolved_owner_prefix = owner_prefix or f"demo-{uuid.uuid4().hex[:8]}"
    result = solve_engineering_goal(
        base_url,
        brief,
        fixture=fixture,
        model_id=model_id,
        wait_timeout_sec=wait_timeout_sec,
        goal_timeout_sec=goal_timeout_sec,
        isolate_dispatch=isolate_dispatch,
        owner_prefix=resolved_owner_prefix,
    )
    return {
        "platform_url": result["platform_url"],
        "poster_agent_id": result["poster_agent_id"],
        "goal_id": result["goal_id"],
        "goal_status": result["goal_status"],
        "goal_kind": result["goal_kind"],
        "verification_spec": result["verification_spec"],
        "model_id": result["model_id"],
        "isolate_dispatch": isolate_dispatch,
        "roles": result.get("roles", []),
        "_agent_credentials": result.get("_agent_credentials", {}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run engineering goal volunteer demo.")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_engineering_goal_demo(
            args.base_url,
            model_id=args.model_id or None,
            wait_timeout_sec=args.wait_sec,
            goal_timeout_sec=args.goal_timeout_sec,
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Engineering goal demo failed: {exc}", file=sys.stderr)
        return 1
    print(f"Engineering goal demo OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
