from __future__ import annotations

import time
from typing import Any

import httpx

from agentswarm_platform.assignment_signing import verify_assignment
from agentswarm_platform.crypto import sign_payload

from agentswarm_sdk.client import AgentClient


def platform_assignment_mode(config: dict[str, Any]) -> str:
    assignment = config.get("assignment")
    if isinstance(assignment, dict) and assignment.get("mode"):
        return str(assignment["mode"])
    return str(config.get("assignment_mode", "pull"))


def fetch_platform_config(base_url: str) -> dict[str, Any]:
    response = httpx.get(f"{base_url.rstrip('/')}/platform/config", timeout=30.0)
    response.raise_for_status()
    return response.json()


def assert_dispatch_mode(base_url: str) -> None:
    mode = platform_assignment_mode(fetch_platform_config(base_url))
    if mode != "dispatch":
        raise RuntimeError(
            f"platform assignment mode is {mode!r}; dispatch client requires dispatch"
        )


def verify_assignment_signature(assignment: dict[str, Any], agent_id: str) -> None:
    payload = assignment.get("signature_payload")
    if not isinstance(payload, dict):
        payload = {
            "lease_id": str(assignment["lease_id"]),
            "agent_id": agent_id,
            "task_id": str(assignment["task_id"]),
            "expires_at": str(assignment["expires_at"]),
        }
    signature = assignment.get("assignment_signature")
    if not signature:
        raise RuntimeError("assignment missing assignment_signature")
    if payload.get("agent_id") != agent_id:
        raise RuntimeError("assignment agent_id mismatch")
    if not verify_assignment(payload, str(signature)):
        raise RuntimeError("invalid assignment signature")


class DispatchClient(AgentClient):
    """Dispatch-mode agent client: presence heartbeats and signed lease assignments."""

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
        if response.is_error:
            detail = response.text
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("detail"):
                    detail = str(body["detail"])
            except ValueError:
                pass
            raise RuntimeError(
                f"task submit failed ({response.status_code}): {detail}"
            )
        return response.json()["submission_id"]
