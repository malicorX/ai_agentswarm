#!/usr/bin/env python3
"""Run a single volunteer role (for local or SSH-started distributed demos)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from demo_volunteer_subjective import (  # noqa: E402
    CLIENT_VERSION,
    connect_volunteer_idle,
    run_volunteer_role,
    wait_for_volunteer_assignment,
)
from agentswarm_agents.volunteer_client import resolve_reported_vram_gb  # noqa: E402


def _wait_for_go_signal(
    go_file: str,
    timeout_sec: float,
    *,
    volunteer=None,
    config=None,
) -> None:
    path = Path(go_file)
    deadline = time.monotonic() + timeout_sec
    heartbeat_interval = 10.0
    last_heartbeat = 0.0
    while time.monotonic() < deadline:
        if path.is_file():
            return
        now = time.monotonic()
        if volunteer is not None and config is not None and now - last_heartbeat >= heartbeat_interval:
            client = volunteer._client
            if client is not None:
                client.heartbeat(
                    config.capabilities,
                    status="idle",
                    model_id=config.model_id,
                    client_version=CLIENT_VERSION,
                    ttl_sec=config.heartbeat_ttl_sec,
                    vram_gb=resolve_reported_vram_gb(config),
                )
            last_heartbeat = now
        time.sleep(0.5)
    raise RuntimeError(f"go signal file not found within {timeout_sec}s: {go_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one volunteer role until assignment completes.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        ),
    )
    parser.add_argument(
        "--capabilities",
        required=True,
        help="Comma-separated capabilities (e.g. coordinator,creative,reviewer)",
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--model-id", default="llm-mock-v1")
    parser.add_argument("--wait-sec", type=float, default=60.0)
    parser.add_argument("--total-wait-sec", type=float, default=600.0)
    parser.add_argument(
        "--go-file",
        default="",
        help="Wait for this file to exist after idle registration (distributed orchestration).",
    )
    parser.add_argument(
        "--go-timeout-sec",
        type=float,
        default=120.0,
        help="Max seconds to wait for --go-file before failing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capabilities = [part.strip() for part in args.capabilities.split(",") if part.strip()]
    if not capabilities:
        print("At least one capability is required", file=sys.stderr)
        return 1

    try:
        if args.go_file:
            volunteer, config = connect_volunteer_idle(
                args.base_url,
                capabilities=capabilities,
                owner=args.owner,
                model_id=args.model_id,
            )
            print("READY", flush=True)
            _wait_for_go_signal(
                args.go_file,
                args.go_timeout_sec,
                volunteer=volunteer,
                config=config,
            )
            from dataclasses import replace

            deadline = time.monotonic() + args.total_wait_sec
            while time.monotonic() < deadline:
                volunteer.config = replace(
                    config, wait_timeout_sec=min(args.wait_sec, 15.0)
                )
                if volunteer.run_once():
                    break
            else:
                raise RuntimeError(
                    f"volunteer {args.owner} did not complete assignment within "
                    f"{args.total_wait_sec}s"
                )
        else:
            run_volunteer_role(
                args.base_url,
                capabilities=capabilities,
                owner=args.owner,
                model_id=args.model_id,
                wait_timeout_sec=args.wait_sec,
                total_wait_sec=args.total_wait_sec,
            )
    except (ValueError, RuntimeError) as exc:
        print(f"Volunteer role failed: {exc}", file=sys.stderr)
        return 1

    print(f"Volunteer role OK: {capabilities} owner={args.owner}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
