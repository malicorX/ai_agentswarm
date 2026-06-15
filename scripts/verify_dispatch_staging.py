#!/usr/bin/env python3
"""Verify dispatch-mode staging API: presence, credits, assignments (Phase 6 close-out)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_platform.crypto import generate_keypair, public_key_b64


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def _register_headers(config_body: dict[str, object]) -> dict[str, str]:
    auth_block = config_body.get("auth")
    if not isinstance(auth_block, dict) or not auth_block.get("enforced"):
        return {}
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip()
    if not bootstrap:
        raise RuntimeError(
            "registration auth is enforced; set AGENTSWARM_BOOTSTRAP_TOKEN for verify"
        )
    return {"X-Bootstrap-Token": bootstrap}


def verify_dispatch_staging(base_url: str, *, timeout: float = 30.0) -> dict[str, str]:
    """Smoke-check dispatch paths on a live staging platform."""
    clean = _clean_url(base_url)
    result: dict[str, str] = {"platform_url": clean}

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        health = client.get(f"{clean}/health")
        health.raise_for_status()
        if health.json() != {"status": "ok"}:
            raise RuntimeError(f"unexpected /health body: {health.json()!r}")

        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        config_body = config.json()
        mode = config_body.get("assignment_mode")
        if mode != "dispatch":
            raise RuntimeError(f"expected assignment_mode=dispatch, got {mode!r}")
        result["assignment_mode"] = str(mode)

        headers = _register_headers(config_body)
        pub, _priv = generate_keypair()
        owner = f"dispatch-verify-{uuid.uuid4().hex[:8]}"
        reg = client.post(
            f"{clean}/agents/register",
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
        result["register"] = str(agent_id)

        presence = client.post(
            f"{clean}/agents/{agent_id}/presence",
            json={
                "status": "idle",
                "capabilities": ["reviewer"],
                "ttl_sec": 60,
            },
        )
        presence.raise_for_status()
        result["presence"] = presence.json().get("status", "ok")

        pending = client.get(f"{clean}/agents/{agent_id}/assignments/pending")
        pending.raise_for_status()
        result["assignments_pending"] = "empty" if pending.json() is None else "assigned"

        credits = client.get(f"{clean}/agents/{agent_id}/credits")
        credits.raise_for_status()
        body = credits.json()
        if not isinstance(body, dict) or "balance" not in body:
            raise RuntimeError(f"unexpected credits response: {body!r}")
        result["credits_balance"] = str(body["balance"])

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
        outcome = verify_dispatch_staging(url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Dispatch staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Dispatch staging OK: {url.strip().rstrip('/')} ({outcome})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
