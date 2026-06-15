#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time

from agentswarm_agents.client import platform_url
from agentswarm_agents.dispatch_client import DispatchClient, mock_capsule_executor
from agentswarm_agents.docker_worker import docker_available, docker_capsule_executor
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
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Execute assignments inside the agentswarm-worker Docker image",
    )
    parser.add_argument(
        "--worker-image",
        default=os.environ.get("AGENTSWARM_WORKER_IMAGE", "agentswarm-worker:dev"),
        help="Docker image tag when --docker is set",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]
    if not capabilities:
        print("At least one capability is required", file=sys.stderr)
        return 2

    if args.docker and not docker_available():
        print(
            "Docker is not available. Install Docker Desktop and build the worker image:\n"
            "  powershell -File scripts/build_worker_image.ps1",
            file=sys.stderr,
        )
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
    executor = (
        docker_capsule_executor(client.agent_id, image=args.worker_image)
        if args.docker
        else mock_capsule_executor
    )
    mode = "docker" if args.docker else "in-process"
    print(f"Executor mode: {mode} (image={args.worker_image if args.docker else 'n/a'})")

    processed = 0
    while True:
        worked = client.run_once(
            capabilities,
            executor,
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
