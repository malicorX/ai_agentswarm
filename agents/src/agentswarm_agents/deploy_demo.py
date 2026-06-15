from __future__ import annotations

import os
import time
from typing import Any, Protocol

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.workers.deployer import build_execution_result, run_deploy_hooks
from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload

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
    owner: str = "deploy-demo",
) -> tuple[str, bytes]:
    pub_raw, priv_raw = generate_keypair()
    response = http.post(
        f"{base}/agents/register",
        json={
            "public_key": public_key_b64(pub_raw),
            "owner": owner,
            "capabilities": capabilities,
        },
    )
    response.raise_for_status()
    return response.json()["agent_id"], priv_raw


def _submit_task(
    http: HttpClient,
    base: str,
    *,
    task_id: str,
    agent_id: str,
    priv: bytes,
    result: dict[str, Any],
) -> None:
    claim = http.post(f"{base}/tasks/{task_id}/claim", json={"agent_id": agent_id})
    claim.raise_for_status()
    token = claim.json()["claim_token"]
    signature = sign_payload(priv, {"task_id": task_id, "result": result})
    submit = http.post(
        f"{base}/tasks/submit",
        json={"claim_token": token, "result": result, "signature": signature},
    )
    submit.raise_for_status()


def run_deploy_demo(http: HttpClient, base_url: str = "") -> None:
    """Exercise deploy request → sign-offs → deploy.execute → deployed."""
    base = base_url.rstrip("/")

    reviewer_a, priv_a = _register_agent(
        http, base, capabilities=["reviewer"], owner="reviewer-a"
    )
    reviewer_b, priv_b = _register_agent(
        http, base, capabilities=["reviewer"], owner="reviewer-b"
    )
    deployer_id, deployer_priv = _register_agent(
        http, base, capabilities=["deployer"], owner="deployer"
    )

    created = http.post(
        f"{base}/deploy/requests",
        json={
            "environment": "staging",
            "artifact_ref": "demo-sha-001",
            "description": "deploy sign-off demo",
            "required_signoffs": 2,
        },
    )
    created.raise_for_status()
    body = created.json()
    request_id = body["request_id"]
    assert body["status"] == "pending"
    assert len(body["approve_task_ids"]) == 2

    for agent_id, priv, task_id in (
        (reviewer_a, priv_a, body["approve_task_ids"][0]),
        (reviewer_b, priv_b, body["approve_task_ids"][1]),
    ):
        _submit_task(
            http,
            base,
            task_id=task_id,
            agent_id=agent_id,
            priv=priv,
            result={"decision": "approve"},
        )

    approved = http.get(f"{base}/deploy/requests/{request_id}")
    approved.raise_for_status()
    approved_body = approved.json()
    assert approved_body["status"] == "approved"
    execute_task_id = approved_body["execute_task_id"]
    assert execute_task_id

    hook_details: dict[str, Any] = {}
    staging_flag = os.environ.get("AGENTSWARM_DEPLOY_STAGING", "").lower()
    if staging_flag in ("1", "true", "yes"):
        hook_details = run_deploy_hooks(approved_body)
    execute_result = build_execution_result(approved_body, hook_details=hook_details)
    _submit_task(
        http,
        base,
        task_id=execute_task_id,
        agent_id=deployer_id,
        priv=deployer_priv,
        result=execute_result,
    )

    deployed = http.get(f"{base}/deploy/requests/{request_id}")
    deployed.raise_for_status()
    final = deployed.json()
    assert final["status"] == "deployed"
    assert final["executed_by_agent_id"] == deployer_id
    assert final["execution_result"]["outcome"] == execute_result["outcome"]
    assert final["signoff_count"] == 2


def main() -> None:
    url = platform_url()
    wait_for_platform(url)
    with httpx.Client(base_url=url, timeout=30.0) as http:
        run_deploy_demo(http)
    print("demo: deploy sign-off flow complete")


if __name__ == "__main__":
    main()
