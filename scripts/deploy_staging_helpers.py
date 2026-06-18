#!/usr/bin/env python3
"""Shared helpers for staging deploy-request and sign-off verification."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from agentswarm_agents.owner_auth import owner_auth_headers
from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _register_agent(
    client: httpx.Client,
    base: str,
    *,
    capabilities: list[str],
    owner: str,
    reg_headers: dict[str, str],
) -> tuple[str, bytes]:
    pub, priv = generate_keypair()
    response = client.post(
        f"{base}/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": owner,
            "capabilities": capabilities,
        },
        headers=reg_headers,
    )
    response.raise_for_status()
    return response.json()["agent_id"], priv


def _submit_task(
    client: httpx.Client,
    base: str,
    *,
    task_id: str,
    agent_id: str,
    priv: bytes,
    result: dict[str, Any],
) -> None:
    claim = client.post(f"{base}/tasks/{task_id}/claim", json={"agent_id": agent_id})
    claim.raise_for_status()
    token = claim.json()["claim_token"]
    signature = sign_payload(priv, {"task_id": task_id, "result": result})
    submit = client.post(
        f"{base}/tasks/submit",
        json={"claim_token": token, "result": result, "signature": signature},
    )
    submit.raise_for_status()


def _ensure_deploy_artifact_ref(
    client: httpx.Client,
    base: str,
    goal_id: str,
    goal_body: dict[str, Any],
    *,
    owner_headers: dict[str, str],
) -> str | None:
    """Return explicit artifact_ref when the verified goal has no deployable primary."""
    primary = goal_body.get("primary_artifact_ref")
    if isinstance(primary, str) and primary.strip():
        return None
    refs = goal_body.get("artifact_refs") or []
    if refs:
        return str(refs[-1])
    marker = f"staging-deploy-e2e:{goal_id}".encode()
    stored = client.post(
        f"{base}/artifacts",
        headers=owner_headers,
        content=marker,
    )
    stored.raise_for_status()
    return str(stored.json()["artifact_ref"])


def request_deploy_from_verified_goal(
    client: httpx.Client,
    base: str,
    goal_id: str,
    *,
    environment: str = "staging",
    required_signoffs: int = 1,
    owner_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST deploy-request for a verified goal; returns deploy body or skip marker."""
    headers = owner_headers or owner_auth_headers()
    if not headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN for deploy-request"
        )
    goal = client.get(f"{base}/creative/goals/{goal_id}", headers=headers)
    goal.raise_for_status()
    goal_body = goal.json()
    if goal_body.get("status") != "verified":
        raise RuntimeError(
            f"goal {goal_id} must be verified before deploy-request, got {goal_body.get('status')!r}"
        )

    artifact_override = _ensure_deploy_artifact_ref(
        client, base, goal_id, goal_body, owner_headers=headers
    )
    deploy_payload: dict[str, Any] = {
        "environment": environment,
        "description": "staging verify deploy from verified goal",
        "required_signoffs": required_signoffs,
    }
    min_cred_raw = os.environ.get("AGENTSWARM_VERIFY_DEPLOY_MIN_CREDIBILITY", "").strip()
    if min_cred_raw:
        deploy_payload["min_credibility"] = float(min_cred_raw)
    if artifact_override:
        deploy_payload["artifact_ref"] = artifact_override

    response = client.post(
        f"{base}/creative/goals/{goal_id}/deploy-request",
        headers=headers,
        json=deploy_payload,
    )
    if response.status_code == 404:
        return {"deploy_from_goal": "skipped_not_deployed"}
    response.raise_for_status()
    body = response.json()
    return {
        "deploy_from_goal": "requested",
        "deploy_request_id": body["request_id"],
        "artifact_ref": body.get("artifact_ref"),
        "goal_id": goal_id,
        "approve_task_ids": list(body.get("approve_task_ids") or []),
    }


def complete_deploy_signoff_chain(
    client: httpx.Client,
    base: str,
    deploy_body: dict[str, Any],
    *,
    reg_headers: dict[str, str] | None = None,
    execute: bool = False,
    signoff_agents: list[tuple[str, bytes]] | None = None,
) -> dict[str, str]:
    """Approve all deploy sign-off tasks; optionally run deploy.execute."""
    request_id = str(deploy_body["deploy_request_id"])
    approve_ids = list(deploy_body.get("approve_task_ids") or [])
    if not approve_ids:
        raise RuntimeError(f"deploy request {request_id} has no approve tasks")

    suffix = uuid.uuid4().hex[:8]
    reviewers: list[tuple[str, bytes, str]] = []
    if signoff_agents:
        if len(signoff_agents) < len(approve_ids):
            raise RuntimeError("not enough signoff agents for approve tasks")
        for index, task_id in enumerate(approve_ids):
            agent_id, priv = signoff_agents[index]
            reviewers.append((agent_id, priv, task_id))
    else:
        for index, task_id in enumerate(approve_ids, start=1):
            agent_id, priv = _register_agent(
                client,
                base,
                capabilities=["reviewer"],
                owner=f"deploy-reviewer-{suffix}-{index}",
                reg_headers=reg_headers or {},
            )
            reviewers.append((agent_id, priv, task_id))

    for agent_id, priv, task_id in reviewers:
        _submit_task(
            client,
            base,
            task_id=task_id,
            agent_id=agent_id,
            priv=priv,
            result={"decision": "approve"},
        )

    approved = client.get(f"{base}/deploy/requests/{request_id}")
    approved.raise_for_status()
    approved_body = approved.json()
    if approved_body.get("status") != "approved":
        raise RuntimeError(
            f"expected deploy request approved, got {approved_body.get('status')!r}"
        )

    result: dict[str, str] = {
        "deploy_signoffs": "ok",
        "deploy_status": "approved",
    }

    if not execute:
        return result

    execute_task_id = approved_body.get("execute_task_id")
    if not execute_task_id:
        raise RuntimeError("approved deploy request missing execute_task_id")

    deployer_id, deployer_priv = _register_agent(
        client,
        base,
        capabilities=["deployer"],
        owner=f"deploy-executor-{suffix}",
        reg_headers=reg_headers or {},
    )
    _submit_task(
        client,
        base,
        task_id=str(execute_task_id),
        agent_id=deployer_id,
        priv=deployer_priv,
        result={
            "outcome": "success",
            "environment": approved_body.get("environment", "staging"),
            "artifact_ref": approved_body.get("artifact_ref"),
            "dry_run": True,
        },
    )
    deployed = client.get(f"{base}/deploy/requests/{request_id}")
    deployed.raise_for_status()
    final = deployed.json()
    if final.get("status") != "deployed":
        raise RuntimeError(f"expected deploy status deployed, got {final.get('status')!r}")
    result["deploy_execute"] = "ok"
    result["deploy_status"] = "deployed"
    return result


def verify_deploy_from_verified_goal_staging(
    base: str,
    goal_id: str,
    *,
    timeout: float = 60.0,
    signoff_agents: list[tuple[str, bytes]] | None = None,
) -> dict[str, str]:
    """Optional post-verify staging check: deploy-request (+ sign-offs when enabled)."""
    if not _env_flag("AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL"):
        return {}

    clean = base.strip().rstrip("/")
    owner_headers = owner_auth_headers()
    if not owner_headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN for deploy verify"
        )

    merged: dict[str, str] = {}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        auth_block = config.json().get("auth")
        reg_headers: dict[str, str] = {}
        if isinstance(auth_block, dict) and auth_block.get("enforced"):
            bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip()
            if bootstrap:
                reg_headers = {"X-Bootstrap-Token": bootstrap}

        deploy_body = request_deploy_from_verified_goal(
            client, clean, goal_id, owner_headers=owner_headers
        )
        merged.update({k: str(v) for k, v in deploy_body.items() if k != "approve_task_ids"})
        if deploy_body.get("deploy_from_goal") != "requested":
            return merged

        if _env_flag("AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN"):
            signoff_result = complete_deploy_signoff_chain(
                client,
                clean,
                deploy_body,
                reg_headers=reg_headers,
                execute=_env_flag("AGENTSWARM_VERIFY_DEPLOY_EXECUTE"),
                signoff_agents=signoff_agents,
            )
            merged.update(signoff_result)

    return merged
