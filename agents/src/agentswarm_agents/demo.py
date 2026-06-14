from __future__ import annotations

import subprocess
import sys
import time

import httpx

from agentswarm_agents.client import platform_url


def wait_for_platform(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"{url}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"platform not reachable at {url}")


def main() -> None:
    url = platform_url()
    wait_for_platform(url)

    httpx.post(
        f"{url}/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "payload": {
                "file": "index.html",
                "insert": "<p id=\"swarm-demo\">Patched by AgentSwarm codewriter.</p>",
            },
        },
    ).raise_for_status()
    print("demo: created codewriter task")

    agents = [
        [sys.executable, "-m", "agentswarm_agents.workers.codewriter", "--once"],
        [sys.executable, "-m", "agentswarm_agents.workers.tester", "--once"],
        [sys.executable, "-m", "agentswarm_agents.workers.reviewer", "--once"],
    ]
    for cmd in agents:
        subprocess.run(cmd, check=True)

    print("demo: phase 0 flow complete")


if __name__ == "__main__":
    main()
