#!/usr/bin/env python3
"""Verify dispatch-mode staging API via the public Python SDK (Phase 20)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "packages" / "sdk-python" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_platform.crypto import generate_keypair
from agentswarm_sdk import (
    AgentClient,
    DispatchClient,
    assert_dispatch_mode,
    fetch_platform_config,
    platform_assignment_mode,
)


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def _register_auth(config_body: dict[str, object]) -> tuple[str | None, str | None]:
    auth_block = config_body.get("auth")
    if not isinstance(auth_block, dict) or not auth_block.get("enforced"):
        return None, None
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip()
    if not bootstrap:
        raise RuntimeError(
            "registration auth is enforced; set AGENTSWARM_BOOTSTRAP_TOKEN for verify"
        )
    return None, bootstrap


def verify_sdk_dispatch_staging(base_url: str, *, timeout: float = 30.0) -> dict[str, str]:
    """Smoke-check dispatch client paths on a live staging platform."""
    clean = _clean_url(base_url)
    result: dict[str, str] = {"platform_url": clean}

    health = httpx.get(f"{clean}/health", timeout=timeout, follow_redirects=True)
    health.raise_for_status()
    if health.json() != {"status": "ok"}:
        raise RuntimeError(f"unexpected /health body: {health.json()!r}")

    assert_dispatch_mode(clean)
    config_body = fetch_platform_config(clean)
    result["assignment_mode"] = platform_assignment_mode(config_body)

    owner_token, bootstrap_token = _register_auth(config_body)
    pub, priv = generate_keypair()
    owner = f"sdk-dispatch-verify-{uuid.uuid4().hex[:8]}"
    client = AgentClient.register(
        clean,
        owner,
        ["reviewer"],
        priv,
        pub,
        owner_token=owner_token,
        bootstrap_token=bootstrap_token,
    )
    result["register"] = client.agent_id

    dispatch = DispatchClient(clean, client.agent_id, priv)
    model_id: str | None = None
    vram_gb: float | None = None
    hardware_block = config_body.get("hardware")
    models_block = config_body.get("models")
    if isinstance(hardware_block, dict) and hardware_block.get("enforced"):
        min_vram = float(hardware_block.get("reviewer_min_vram_gb", 6.0))
        allowlist = (
            models_block.get("allowlist") if isinstance(models_block, dict) else None
        )
        first_model = allowlist[0] if isinstance(allowlist, list) and allowlist else {}
        model_id = (
            str(first_model["id"])
            if isinstance(first_model, dict) and first_model.get("id")
            else "llm-mock-v1"
        )
        vram_gb = max(8.0, min_vram)
        result["hardware_gates"] = "enforced"

    presence = dispatch.heartbeat(
        ["reviewer"],
        status="idle",
        ttl_sec=60,
        model_id=model_id,
        vram_gb=vram_gb,
    )
    result["presence"] = str(presence.get("status", "ok"))

    pending = dispatch.get_pending_assignment()
    result["assignments_pending"] = "empty" if pending is None else "assigned"

    credits = httpx.get(f"{clean}/agents/{client.agent_id}/credits", timeout=timeout)
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
        outcome = verify_sdk_dispatch_staging(url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"SDK dispatch staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"SDK dispatch staging OK: {url.strip().rstrip('/')} ({outcome})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
