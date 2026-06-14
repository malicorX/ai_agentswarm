from __future__ import annotations

import os
from typing import Any

import httpx

from agentswarm_platform.crypto import public_key_b64, sign_payload


class AgentClient:
    """REST client for external AgentSwarm agents (Phase 1)."""

    def __init__(
        self,
        base_url: str,
        agent_id: str,
        private_key: bytes,
        *,
        owner_token: str | None = None,
        bootstrap_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.private_key = private_key
        self._owner_token = owner_token or os.environ.get("AGENTSWARM_OWNER_TOKEN")
        self._bootstrap_token = bootstrap_token or os.environ.get(
            "AGENTSWARM_BOOTSTRAP_TOKEN"
        )
        self._http = httpx.Client(base_url=self.base_url, timeout=30.0)

    def _owner_headers(self) -> dict[str, str]:
        if self._owner_token:
            return {"Authorization": f"Bearer {self._owner_token}"}
        if self._bootstrap_token:
            return {"X-Bootstrap-Token": self._bootstrap_token}
        return {}

    @classmethod
    def register(
        cls,
        base_url: str,
        owner: str,
        capabilities: list[str],
        private_key: bytes,
        public_key_raw: bytes,
        *,
        owner_token: str | None = None,
        bootstrap_token: str | None = None,
        project_ids: list[str] | None = None,
    ) -> AgentClient:
        headers: dict[str, str] = {}
        token = owner_token or os.environ.get("AGENTSWARM_OWNER_TOKEN")
        bootstrap = bootstrap_token or os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif bootstrap:
            headers["X-Bootstrap-Token"] = bootstrap

        payload = {
            "public_key": public_key_b64(public_key_raw),
            "owner": owner,
            "capabilities": capabilities,
        }
        if project_ids is not None:
            payload["project_ids"] = project_ids

        response = httpx.post(
            f"{base_url.rstrip('/')}/agents/register",
            json=payload,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        agent_id = response.json()["agent_id"]
        return cls(
            base_url,
            agent_id,
            private_key,
            owner_token=token,
            bootstrap_token=bootstrap,
        )

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
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "task_type": task_type,
            "capability_required": capability_required,
            "payload": payload,
        }
        if project_id is not None:
            body["project_id"] = project_id
        response = self._http.post(
            "/tasks",
            json=body,
            headers=self._owner_headers(),
        )
        response.raise_for_status()
        return response.json()
