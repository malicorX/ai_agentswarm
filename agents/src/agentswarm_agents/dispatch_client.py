from __future__ import annotations

import time
from typing import Any, Callable

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.client import PlatformClient
from agentswarm_agents.docker_worker import verify_assignment_signature
from agentswarm_platform.crypto import sign_payload

CapsuleExecutor = Callable[[dict[str, Any]], dict[str, Any]]


class DispatchClient(PlatformClient):
    def heartbeat(
        self,
        capabilities: list[str],
        *,
        status: str = "idle",
        model_id: str | None = None,
        load: float = 0.0,
        client_version: str | None = None,
        ttl_sec: int = 120,
        vram_gb: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": status,
            "capabilities": capabilities,
            "model_id": model_id,
            "load": load,
            "client_version": client_version,
            "ttl_sec": ttl_sec,
        }
        if vram_gb is not None:
            payload["vram_gb"] = vram_gb
        response = self._http.post(
            f"/agents/{self.agent_id}/presence",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def get_pending_assignment(self, *, wait_sec: float = 0) -> dict[str, Any] | None:
        params: dict[str, float] = {}
        if wait_sec > 0:
            params["wait_sec"] = wait_sec
        timeout = max(30.0, wait_sec + 10.0) if wait_sec > 0 else 30.0
        response = self._http.get(
            f"/agents/{self.agent_id}/assignments/pending",
            params=params or None,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def wait_for_assignment(
        self,
        *,
        poll_sec: float = 1.0,
        timeout_sec: float = 30.0,
        server_long_poll: bool = True,
    ) -> dict[str, Any] | None:
        if server_long_poll:
            return self.get_pending_assignment(wait_sec=timeout_sec)
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            assignment = self.get_pending_assignment()
            if assignment is not None:
                return assignment
            time.sleep(poll_sec)
        return None

    def submit_assignment(
        self,
        assignment: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        claim_token = assignment["claim_token"]
        task_id = assignment["task_id"]
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

    def run_once(
        self,
        capabilities: list[str],
        executor: CapsuleExecutor,
        *,
        poll_sec: float = 1.0,
        wait_timeout_sec: float = 30.0,
        model_id: str | None = None,
        client_version: str | None = None,
        verify_signature: bool = True,
    ) -> bool:
        self.heartbeat(
            capabilities,
            status="idle",
            model_id=model_id,
            client_version=client_version,
        )
        assignment = self.wait_for_assignment(
            poll_sec=poll_sec, timeout_sec=wait_timeout_sec
        )
        if assignment is None:
            return False
        if verify_signature:
            verify_assignment_signature(assignment, self.agent_id)
        result = executor(assignment)
        self.submit_assignment(assignment, result)
        self.heartbeat(
            capabilities,
            status="idle",
            model_id=model_id,
            client_version=client_version,
        )
        return True


def mock_capsule_executor(assignment: dict[str, Any]) -> dict[str, Any]:
    return execute_capsule(assignment)
