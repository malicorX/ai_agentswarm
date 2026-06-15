#!/usr/bin/env python3
"""Live staging verify: stale presence reclaims assignment leases (P11.0)."""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_platform.crypto import generate_keypair, public_key_b64


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def _auth_headers(config_body: dict[str, object]) -> dict[str, str]:
    auth_block = config_body.get("auth")
    if not isinstance(auth_block, dict) or not auth_block.get("enforced"):
        return {}
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip()
    if not bootstrap:
        raise RuntimeError(
            "registration auth is enforced; set AGENTSWARM_BOOTSTRAP_TOKEN for verify"
        )
    return {"X-Bootstrap-Token": bootstrap}


def _presence_payload(
    config_body: dict[str, object],
    *,
    ttl_sec: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "idle",
        "capabilities": ["reviewer"],
        "ttl_sec": ttl_sec,
    }
    hardware_block = config_body.get("hardware")
    models_block = config_body.get("models")
    if isinstance(hardware_block, dict) and hardware_block.get("enforced"):
        min_vram = float(hardware_block.get("reviewer_min_vram_gb", 6.0))
        model_id = "llm-mock-v1"
        if isinstance(models_block, dict):
            allowlist = models_block.get("allowlist")
            if isinstance(allowlist, list) and allowlist:
                first = allowlist[0]
                if isinstance(first, dict) and first.get("id"):
                    model_id = str(first["id"])
        payload["model_id"] = model_id
        payload["vram_gb"] = max(8.0, min_vram)
    return payload


def _register_reviewer(
    client: httpx.Client,
    base_url: str,
    *,
    owner: str,
    headers: dict[str, str],
) -> str:
    pub, _priv = generate_keypair()
    reg = client.post(
        f"{base_url}/agents/register",
        json={
            "public_key": public_key_b64(pub),
            "owner": owner,
            "capabilities": ["reviewer"],
        },
        headers=headers,
    )
    reg.raise_for_status()
    agent_id = reg.json().get("agent_id")
    if not agent_id:
        raise RuntimeError("register response missing agent_id")
    return str(agent_id)


def verify_lease_reclaim_staging(
    base_url: str,
    *,
    timeout: float = 90.0,
    presence_ttl_sec: int = 5,
    stale_wait_sec: float | None = None,
    assignment_wait_sec: float = 20.0,
) -> dict[str, str]:
    """Prove stale presence triggers lease reclaim and redispatch on staging."""
    clean = _clean_url(base_url)
    if stale_wait_sec is None:
        stale_wait_sec = float(
            os.environ.get(
                "AGENTSWARM_VERIFY_LEASE_STALE_WAIT_SEC",
                str(presence_ttl_sec + 10),
            )
        )
    run_id = uuid.uuid4().hex[:8]
    owner_a = f"lease-reclaim-{run_id}-a"
    owner_b = f"lease-reclaim-{run_id}-b"
    include_owners = [owner_a, owner_b]
    result: dict[str, str] = {
        "platform_url": clean,
        "run_id": run_id,
    }

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        config_body = config.json()
        if config_body.get("assignment_mode") != "dispatch":
            raise RuntimeError(
                f"expected assignment_mode=dispatch, got {config_body.get('assignment_mode')!r}"
            )
        dispatch_block = config_body.get("dispatch")
        if isinstance(dispatch_block, dict) and "lease_ttl_minutes" in dispatch_block:
            result["lease_ttl_minutes"] = str(dispatch_block["lease_ttl_minutes"])

        headers = _auth_headers(config_body)
        agent_a = _register_reviewer(client, clean, owner=owner_a, headers=headers)
        agent_b = _register_reviewer(client, clean, owner=owner_b, headers=headers)
        result["agent_a"] = agent_a
        result["agent_b"] = agent_b

        presence_a = _presence_payload(config_body, ttl_sec=presence_ttl_sec)
        client.post(
            f"{clean}/agents/{agent_a}/presence",
            json=presence_a,
        ).raise_for_status()

        need = client.post(
            f"{clean}/pool/need",
            json={
                "role": "reviewer",
                "capability_required": "reviewer",
                "task_type": "reviewer.subjective",
                "payload": {
                    "capsule": {
                        "brief": "Lease reclaim staging verify",
                        "rubric": [{"id": "quality", "weight": 1.0}],
                    }
                },
                "constraints": {"include_owners": include_owners},
            },
            headers=headers,
        )
        need.raise_for_status()
        need_body = need.json()
        if not need_body.get("assigned"):
            raise RuntimeError("expected pool need to assign to reviewer A")
        task_id = str(need_body["task_id"])
        result["task_id"] = task_id

        pending_a = client.get(f"{clean}/agents/{agent_a}/assignments/pending").json()
        if pending_a is None or str(pending_a.get("task_id")) != task_id:
            raise RuntimeError("reviewer A did not receive the assignment")

        time.sleep(stale_wait_sec)

        # Reconcile orphaned claimed tasks / assigned needs after stale reclaim.
        client.get(f"{clean}/agents/{agent_a}/assignments/pending")
        if client.get(f"{clean}/agents/{agent_a}/assignments/pending").json() is not None:
            raise RuntimeError("reviewer A still holds assignment after stale window")

        presence_b = _presence_payload(config_body, ttl_sec=120)
        client.post(
            f"{clean}/agents/{agent_b}/presence",
            json=presence_b,
        ).raise_for_status()

        redispatch = client.post(
            f"{clean}/pool/need",
            json={
                "role": "reviewer",
                "capability_required": "reviewer",
                "task_id": task_id,
                "constraints": {"include_owners": [owner_b]},
            },
            headers=headers,
        )
        redispatch.raise_for_status()
        redispatch_body = redispatch.json()
        if not redispatch_body.get("assigned"):
            raise RuntimeError("expected reclaimed task to redispatch to reviewer B")

        reclaimed = client.get(
            f"{clean}/agents/{agent_b}/assignments/pending",
            params={"wait_sec": assignment_wait_sec},
        ).json()
        if reclaimed is None or str(reclaimed.get("task_id")) != task_id:
            raise RuntimeError(
                "reviewer B did not receive reclaimed assignment "
                f"(got {reclaimed!r})"
            )

        released = client.get(f"{clean}/agents/{agent_a}/assignments/pending").json()
        if released is not None:
            raise RuntimeError("reviewer A still holds an assignment after stale reclaim")

    result["stale_reclaim"] = "ok"
    return result


def main() -> int:
    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        )
    )
    try:
        outcome = verify_lease_reclaim_staging(url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Lease reclaim staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Lease reclaim staging OK: {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
