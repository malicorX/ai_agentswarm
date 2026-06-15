from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx

from agentswarm_platform.crypto import public_key_b64, sign_payload

PROTOCOL_TOOL_NAMES = (
    "agentswarm_register",
    "agentswarm_poll_tasks",
    "agentswarm_claim_task",
    "agentswarm_checkpoint",
    "agentswarm_submit",
    "agentswarm_poll_verifications",
    "agentswarm_claim_verification",
    "agentswarm_verify",
)


def platform_url(explicit: str | None = None) -> str:
    return (explicit or os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000")).rstrip(
        "/"
    )


def owner_auth_headers() -> dict[str, str]:
    owner_token = os.environ.get("AGENTSWARM_OWNER_TOKEN", "")
    if owner_token:
        return {"Authorization": f"Bearer {owner_token}"}
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "")
    if bootstrap:
        return {"X-Bootstrap-Token": bootstrap}
    return {}


def decode_private_key(private_key_b64: str | None) -> bytes:
    raw = private_key_b64 or os.environ.get("AGENTSWARM_PRIVATE_KEY_B64", "")
    if not raw:
        raise ValueError(
            "private_key_b64 required (or set AGENTSWARM_PRIVATE_KEY_B64)"
        )
    return base64.urlsafe_b64decode(raw.encode("ascii"))


def _parse_json_object(value: str | dict[str, Any], field: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} must be valid JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object")
    return parsed


def register_agent(
    *,
    owner: str,
    capabilities: list[str],
    public_key_b64: str,
    base_url: str | None = None,
    project_ids: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "public_key": public_key_b64,
        "owner": owner,
        "capabilities": capabilities,
    }
    if project_ids:
        body["project_ids"] = project_ids
    response = httpx.post(
        f"{platform_url(base_url)}/agents/register",
        json=body,
        headers=owner_auth_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def poll_tasks(
    *,
    agent_id: str,
    capability: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {"agent_id": agent_id}
    if capability:
        params["capability"] = capability
    response = httpx.get(
        f"{platform_url(base_url)}/tasks/poll",
        params=params,
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError("unexpected poll_tasks response")
    return data


def claim_task(
    *,
    agent_id: str,
    task_id: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    response = httpx.post(
        f"{platform_url(base_url)}/tasks/{task_id}/claim",
        json={"agent_id": agent_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def checkpoint_task(
    *,
    claim_token: str,
    partial_state: dict[str, Any] | str,
    base_url: str | None = None,
) -> dict[str, Any]:
    state = _parse_json_object(partial_state, "partial_state")
    response = httpx.post(
        f"{platform_url(base_url)}/tasks/checkpoint",
        json={"claim_token": claim_token, "partial_state": state},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def submit_task(
    *,
    claim_token: str,
    task_id: str,
    result: dict[str, Any] | str,
    private_key_b64: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    payload = _parse_json_object(result, "result")
    private_key = decode_private_key(private_key_b64)
    signature = sign_payload(private_key, {"task_id": task_id, "result": payload})
    response = httpx.post(
        f"{platform_url(base_url)}/tasks/submit",
        json={
            "claim_token": claim_token,
            "result": payload,
            "signature": signature,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def poll_verifications(
    *,
    agent_id: str,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{platform_url(base_url)}/verifications/poll",
        params={"agent_id": agent_id},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError("unexpected poll_verifications response")
    return data


def claim_verification(
    *,
    agent_id: str,
    verification_id: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    response = httpx.post(
        f"{platform_url(base_url)}/verifications/{verification_id}/claim",
        json={"agent_id": agent_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def verify_submission(
    *,
    claim_token: str,
    verdict: str,
    task_id: str,
    submission_id: str,
    notes: str = "",
    private_key_b64: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    private_key = decode_private_key(private_key_b64)
    signed = {
        "task_id": task_id,
        "submission_id": submission_id,
        "verdict": verdict,
        "notes": notes,
    }
    signature = sign_payload(private_key, signed)
    response = httpx.post(
        f"{platform_url(base_url)}/verifications/verify",
        json={
            "claim_token": claim_token,
            "verdict": verdict,
            "notes": notes,
            "signature": signature,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def platform_health(*, base_url: str | None = None) -> dict[str, Any]:
    response = httpx.get(f"{platform_url(base_url)}/health", timeout=30.0)
    response.raise_for_status()
    return response.json()


def generate_keypair_b64() -> tuple[str, str]:
    from agentswarm_platform.crypto import generate_keypair

    pub, priv = generate_keypair()
    return (
        public_key_b64(pub),
        base64.urlsafe_b64encode(priv).decode("ascii"),
    )
