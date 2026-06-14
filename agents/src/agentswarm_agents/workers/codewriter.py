from __future__ import annotations

import argparse
import time
from pathlib import Path

from agentswarm_platform.crypto import generate_keypair

from agentswarm_agents.client import PlatformClient, pilot_dir, platform_url


def apply_patch(payload: dict) -> dict:
    rel_path = payload["file"]
    marker = payload.get("marker", "<!-- agentswarm -->")
    target = Path(pilot_dir()) / rel_path
    if not target.exists():
        raise FileNotFoundError(f"pilot file not found: {target}")
    content = target.read_text(encoding="utf-8")
    if marker in content:
        new_content = content.replace(marker, f"{marker}\n{payload.get('insert', '')}")
    else:
        new_content = content + f"\n{marker}\n{payload.get('insert', '')}\n"
    target.write_text(new_content, encoding="utf-8")
    return {"file": rel_path, "applied": True, "bytes_written": len(new_content)}


def run_once(client: PlatformClient) -> bool:
    tasks = client.poll_tasks(capability="codewriter")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = apply_patch(task["payload"])
    client.submit(claim_token, task["task_id"], result)
    print(f"codewriter: completed {task['task_id']}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm codewriter agent")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    pub, priv = generate_keypair()
    client = PlatformClient.register(
        platform_url(),
        owner="phase0-codewriter",
        capabilities=["codewriter"],
        private_key=priv,
        public_key_raw=pub,
    )
    print(f"codewriter registered: {client.agent_id}")

    if args.once:
        if not run_once(client):
            print("codewriter: no tasks")
        return

    while True:
        if run_once(client):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
