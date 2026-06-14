from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.memory_keys import memory_key_for_project
from agentswarm_platform.crypto import generate_keypair, public_key_b64


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...

    def post(self, url: str, **kwargs: Any) -> Any: ...


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


def _register_agent(
    http: HttpClient,
    base: str,
    *,
    capabilities: list[str],
    project_ids: list[str],
    owner: str = "federation-demo",
) -> str:
    pub_raw, _priv_raw = generate_keypair()
    response = http.post(
        f"{base}/agents/register",
        json={
            "public_key": public_key_b64(pub_raw),
            "owner": owner,
            "capabilities": capabilities,
            "project_ids": project_ids,
        },
    )
    response.raise_for_status()
    return response.json()["agent_id"]


def run_federation_demo(http: HttpClient, base_url: str = "") -> None:
    """Exercise multi-project memory, bootstrap, and scoped task polling."""
    base = base_url.rstrip("/")
    project_id = "federation-demo"

    create = http.post(
        f"{base}/projects",
        json={
            "project_id": project_id,
            "name": "Federation Demo Hub",
            "governance_template_id": "news-hub",
        },
    )
    create.raise_for_status()
    project = create.json()
    assert project["project_id"] == project_id

    memory_key = memory_key_for_project(project_id)
    assert memory_key == f"{project_id}.news-backlog"

    memory = http.get(f"{base}/memory/{memory_key}")
    memory.raise_for_status()
    assert memory.json()["content"]["articles"] == []

    governance = http.get(f"{base}/projects/{project_id}/governance")
    governance.raise_for_status()
    assert governance.json()["governance_template_id"] == "news-hub"

    regional_agent = _register_agent(
        http,
        base,
        capabilities=["codewriter", "orchestrator"],
        project_ids=[project_id],
    )
    default_agent = _register_agent(
        http,
        base,
        capabilities=["codewriter"],
        project_ids=["default"],
        owner="default-only",
    )

    task = http.post(
        f"{base}/tasks",
        json={
            "task_type": "codewriter.patch",
            "capability_required": "codewriter",
            "project_id": project_id,
            "payload": {"file": "index.html", "insert": "<!-- federation-demo -->"},
        },
    )
    task.raise_for_status()
    task_id = task.json()["task_id"]
    assert task.json()["project_id"] == project_id

    regional_poll = http.get(
        f"{base}/tasks/poll",
        params={"agent_id": regional_agent, "capability": "codewriter"},
    )
    regional_poll.raise_for_status()
    regional_ids = {item["task_id"] for item in regional_poll.json()}
    assert task_id in regional_ids

    default_poll = http.get(
        f"{base}/tasks/poll",
        params={"agent_id": default_agent, "capability": "codewriter"},
    )
    default_poll.raise_for_status()
    default_ids = {item["task_id"] for item in default_poll.json()}
    assert task_id not in default_ids

    orchestrator_poll = http.get(
        f"{base}/tasks/poll",
        params={"agent_id": regional_agent, "capability": "orchestrator"},
    )
    orchestrator_poll.raise_for_status()
    bootstrap_scans = [
        item
        for item in orchestrator_poll.json()
        if item["task_type"] == "orchestrator.scan"
        and item.get("project_id") == project_id
    ]
    assert bootstrap_scans, "expected bootstrap orchestrator.scan for new project"

    summary = http.get(f"{base}/platform/summary")
    summary.raise_for_status()
    memory_keys = summary.json().get("memory_keys") or []
    assert memory_key in memory_keys


def main() -> None:
    url = platform_url()
    wait_for_platform(url)
    with httpx.Client(base_url=url, timeout=30.0) as http:
        run_federation_demo(http)
    print("demo: federation flow complete")


if __name__ == "__main__":
    main()
