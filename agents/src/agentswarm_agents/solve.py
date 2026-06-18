"""AgentSwarm solve CLI — post a problem and run the volunteer team, or work the task pool."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import uuid

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.engineering_goal import (
    build_engineering_roles,
    list_fixtures,
    solve_engineering_goal,
)
from agentswarm_agents.volunteer_team import (
    clean_platform_url,
    run_volunteer_workers_until_stopped,
    validate_dispatch_platform,
)


def _parse_capabilities(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _engineering_team_roles(owner_prefix: str) -> list[tuple[list[str], str]]:
    run_id = uuid.uuid4().hex[:8]
    return build_engineering_roles(run_id, owner_prefix=owner_prefix)


def cmd_fixtures(_args: argparse.Namespace) -> int:
    for name in list_fixtures():
        print(name)
    return 0


def cmd_solve(args: argparse.Namespace) -> int:
    brief = args.brief.strip()
    if not brief:
        print("Describe the task to solve, e.g. agentswarm-solve implement fizzbuzz", file=sys.stderr)
        return 1
    try:
        result = solve_engineering_goal(
            args.base_url,
            brief,
            fixture=args.fixture,
            model_id=args.model_id or None,
            wait_timeout_sec=args.wait_sec,
            goal_timeout_sec=args.goal_timeout_sec,
            owner_prefix=args.owner_prefix,
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"solve failed: {exc}", file=sys.stderr)
        return 1

    print("Task verified.")
    print(f"  goal_id: {result['goal_id']}")
    print(f"  fixture: {result['verification_spec']['fixture']}")
    print(f"  brief:   {result['brief']}")
    if result.get("artifact_text"):
        print("  artifact:")
        for line in str(result["artifact_text"]).splitlines()[:20]:
            print(f"    {line}")
    return 0


def cmd_work(args: argparse.Namespace) -> int:
    base_url = clean_platform_url(args.base_url)
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            config = client.get(f"{base_url}/platform/config")
            config.raise_for_status()
            model_id = args.model_id or validate_dispatch_platform(config.json())
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"work failed: {exc}", file=sys.stderr)
        return 1

    if args.team == "engineering":
        roles = _engineering_team_roles(args.owner_prefix)
    else:
        caps = _parse_capabilities(args.capabilities)
        if not caps:
            print("Provide --capabilities or --team engineering", file=sys.stderr)
            return 1
        run_id = uuid.uuid4().hex[:8]
        roles = [(caps, f"{args.owner_prefix}-{'-'.join(caps)}-{run_id}")]

    stop = threading.Event()

    def _handle_signal(*_args: object) -> None:
        print("\nStopping workers...", flush=True)
        stop.set()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    print(f"AgentSwarm work mode — platform {base_url}")
    print("Waiting for dispatch assignments (Ctrl+C to stop).")
    for _caps, owner in roles:
        print(f"  worker: {owner}")

    run_volunteer_workers_until_stopped(
        base_url,
        roles=roles,
        model_id=model_id,
        wait_timeout_sec=args.wait_sec,
        stop=stop,
    )
    return 0


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", platform_url()),
        ),
    )
    parser.add_argument("--model-id", default=os.environ.get("AGENTSWARM_MODEL_ID", ""))
    parser.add_argument("--wait-sec", type=float, default=60.0)
    parser.add_argument("--goal-timeout-sec", type=float, default=300.0)
    parser.add_argument("--owner-prefix", default="solve")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentswarm-solve",
        description=(
            "Solve engineering tasks via the AgentSwarm volunteer pipeline, "
            "or run workers that pick up platform assignments."
        ),
    )
    _add_common_args(parser)
    parser.add_argument(
        "--fixture",
        default=os.environ.get("AGENTSWARM_ENGINEERING_FIXTURE", "primes"),
        choices=list_fixtures(),
        help="Engineering-lab fixture used for automated verification",
    )
    parser.add_argument(
        "brief",
        nargs="*",
        help='Task brief (default mode), or "work" / "fixtures" subcommand',
    )
    parser.add_argument(
        "--team",
        choices=("engineering",),
        default=None,
        help="Predefined capability team for work mode",
    )
    parser.add_argument(
        "--capabilities",
        default="",
        help="Comma-separated capabilities for a single worker in work mode",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.brief and args.brief[0] == "work":
        args.brief = args.brief[1:]
        return cmd_work(args)
    if args.brief and args.brief[0] == "fixtures":
        return cmd_fixtures(args)

    args.brief = " ".join(args.brief)
    return cmd_solve(args)


if __name__ == "__main__":
    raise SystemExit(main())
