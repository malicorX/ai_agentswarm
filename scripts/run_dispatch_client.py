#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time

from agentswarm_agents.client import platform_url
from agentswarm_agents.dispatch_client import DispatchClient, mock_capsule_executor
from agentswarm_platform.crypto import generate_keypair


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a dev dispatch client (heartbeat, wait, mock execute)."
    )
    parser.add_argument(
        "--base-url",
        default=platform_url(),
        help="Platform API base URL",
    )
    parser.add_argument(
        "--owner",
        default=os.environ.get("AGENTSWARM_OWNER", "dispatch-dev"),
        help="Owner label for registration",
    )
    parser.add_argument(
        "--capabilities",
        default=os.environ.get("AGENTSWARM_CAPABILITIES", "reviewer"),
        help="Comma-separated capabilities",
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=0,
        help="Max assignments to process (0 = run until idle timeout each loop)",
    )
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=1.0,
        help="Poll interval while waiting for assignment",
    )
    parser.add_argument(
        "--wait-sec",
        type=float,
        default=30.0,
        help="Max seconds to wait per loop for an assignment",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]
    if not capabilities:
        print("At least one capability is required", file=sys.stderr)
        return 2

    pub_raw, priv_raw = generate_keypair()
    client = DispatchClient.register(
        args.base_url,
        owner=args.owner,
        capabilities=capabilities,
        private_key=priv_raw,
        public_key_raw=pub_raw,
    )
    print(f"Registered agent {client.agent_id} capabilities={capabilities}")

    processed = 0
    while True:
        worked = client.run_once(
            capabilities,
            mock_capsule_executor,
            poll_sec=args.poll_sec,
            wait_timeout_sec=args.wait_sec,
        )
        if worked:
            processed += 1
            print(f"Completed assignment #{processed}")
            if args.loops and processed >= args.loops:
                break
        else:
            print("No assignment within timeout; sleeping 2s")
            time.sleep(2.0)
            if args.loops and processed >= args.loops:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
