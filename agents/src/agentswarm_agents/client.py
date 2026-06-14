from __future__ import annotations

import json
import os
from typing import Any

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers
from agentswarm_platform.crypto import public_key_b64, sign_payload


class PlatformClient:
    def __init__(self, base_url: str, agent_id: str, private_key: bytes) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.private_key = private_key
        self._http = httpx.Client(base_url=self.base_url, timeout=30.0)

    @classmethod
    def register(
        cls,
        base_url: str,
        owner: str,
        capabilities: list[str],
        private_key: bytes,
        public_key_raw: bytes,
    ) -> PlatformClient:
        response = httpx.post(
            f"{base_url.rstrip('/')}/agents/register",
            json={
                "public_key": public_key_b64(public_key_raw),
                "owner": owner,
                "capabilities": capabilities,
            },
        )
        response.raise_for_status()
        agent_id = response.json()["agent_id"]
        return cls(base_url, agent_id, private_key)

    def poll_tasks(self, capability: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {"agent_id": self.agent_id}
        if capability:
            params["capability"] = capability
        response = self._http.get("/tasks/poll", params=params)
        response.raise_for_status()
        return response.json()

    def claim(self, task_id: str) -> str:
        response = self._http.post(
            f"/tasks/{task_id}/claim",
            json={"agent_id": self.agent_id},
        )
        response.raise_for_status()
        return response.json()["claim_token"]

    def submit(self, claim_token: str, task_id: str, result: dict[str, Any]) -> str:
        signature = sign_payload(
            self.private_key, {"task_id": task_id, "result": result}
        )
        response = self._http.post(
            "/tasks/submit",
            json={
                "claim_token": claim_token,
                "result": result,
                "signature": signature,
            },
        )
        response.raise_for_status()
        return response.json()["submission_id"]

    def create_task(
        self,
        task_type: str,
        capability_required: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._http.post(
            "/tasks",
            json={
                "task_type": task_type,
                "capability_required": capability_required,
                "payload": payload,
            },
            headers=owner_auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    def upsert_memory(
        self,
        memory_key: str,
        content: dict[str, Any],
        *,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        tag_list = tags or []
        signature = sign_payload(
            self.private_key,
            {
                "memory_key": memory_key,
                "content": content,
                "tags": tag_list,
                "agent_id": self.agent_id,
            },
        )
        response = self._http.put(
            f"/memory/{memory_key}",
            json={
                "key": memory_key,
                "content": content,
                "tags": tag_list,
                "agent_id": self.agent_id,
                "signature": signature,
            },
        )
        response.raise_for_status()
        return response.json()


def repo_root() -> str:
    return os.environ.get(
        "AGENTSWARM_REPO_ROOT",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
    )


def pilot_dir() -> str:
    return os.path.join(repo_root(), "pilot", "news-hub")


def platform_url() -> str:
    return os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000")
