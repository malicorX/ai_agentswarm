from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from agentswarm_platform.crypto import generate_keypair

from agentswarm_agents.client import PlatformClient, pilot_dir, platform_url


def run_pytest() -> dict:
    pilot = Path(pilot_dir())
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=pilot,
        capture_output=True,
        text=True,
    )
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def run_once(client: PlatformClient) -> bool:
    tasks = client.poll_tasks(capability="tester")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = run_pytest()
    client.submit(claim_token, task["task_id"], result)
    print(f"tester: completed {task['task_id']} passed={result['passed']}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm tester agent")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    pub, priv = generate_keypair()
    client = PlatformClient.register(
        platform_url(),
        owner="phase0-tester",
        capabilities=["tester"],
        private_key=priv,
        public_key_raw=pub,
    )
    print(f"tester registered: {client.agent_id}")

    if args.once:
        if not run_once(client):
            print("tester: no tasks")
        return

    while True:
        if run_once(client):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
