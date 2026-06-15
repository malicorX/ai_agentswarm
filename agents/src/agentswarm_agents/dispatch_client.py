from __future__ import annotations

import time
from typing import Any, Callable

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.client import PlatformClient
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
    ) -> dict[str, Any]:
        response = self._http.post(
            f"/agents/{self.agent_id}/presence",
            json={
                "status": status,
                "capabilities": capabilities,
                "model_id": model_id,
                "load": load,
                "client_version": client_version,
                "ttl_sec": ttl_sec,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_pending_assignment(self) -> dict[str, Any] | None:
        response = self._http.get(f"/agents/{self.agent_id}/assignments/pending")
        response.raise_for_status()
        return response.json()

    def wait_for_assignment(
        self,
        *,
        poll_sec: float = 1.0,
        timeout_sec: float = 30.0,
    ) -> dict[str, Any] | None:
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
    ) -> bool:
        self.heartbeat(capabilities, status="idle")
        assignment = self.wait_for_assignment(
            poll_sec=poll_sec, timeout_sec=wait_timeout_sec
        )
        if assignment is None:
            return False
        result = executor(assignment)
        self.submit_assignment(assignment, result)
        self.heartbeat(capabilities, status="idle")
        return True


def mock_capsule_executor(assignment: dict[str, Any]) -> dict[str, Any]:
    return execute_capsule(assignment)
