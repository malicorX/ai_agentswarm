#!/usr/bin/env python3
"""Verify reviewer VRAM hardware gates on staging (P9.1)."""

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


def verify_hardware_gates_staging(
    base_url: str,
    *,
    expect_enforced: bool | None = None,
    timeout: float = 30.0,
) -> dict[str, str]:
    clean = _clean_url(base_url)
    result: dict[str, str] = {"platform_url": clean}

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        config_body = config.json()
        hardware_block = config_body.get("hardware")
        if not isinstance(hardware_block, dict):
            raise RuntimeError("platform config missing hardware block")
        enforced = bool(hardware_block.get("enforced"))
        result["hardware_enforced"] = str(enforced)
        min_vram = hardware_block.get("reviewer_min_vram_gb")
        if min_vram is None:
            raise RuntimeError("platform config missing hardware.reviewer_min_vram_gb")
        result["reviewer_min_vram_gb"] = str(min_vram)

        if expect_enforced is True and not enforced:
            raise RuntimeError("expected hardware.enforced=true on staging")
        if expect_enforced is False and enforced:
            raise RuntimeError("expected hardware.enforced=false on staging")

        if not enforced:
            result["low_vram_rejected"] = "skipped"
            return result

        headers = _register_headers(config_body)
        pub, _priv = generate_keypair()
        suffix = uuid.uuid4().hex[:8]
        reg = client.post(
            f"{clean}/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"hw-gate-{suffix}",
                "capabilities": ["reviewer"],
            },
            headers=headers,
        )
        reg.raise_for_status()
        agent_id = reg.json()["agent_id"]

        missing = client.post(
            f"{clean}/agents/{agent_id}/presence",
            json={
                "status": "idle",
                "capabilities": ["reviewer"],
                "model_id": "llm-mock-v1",
                "ttl_sec": 60,
            },
        )
        if missing.status_code != 400:
            raise RuntimeError(
                f"expected reviewer presence without vram_gb to be rejected, got {missing.status_code}"
            )

        low = client.post(
            f"{clean}/agents/{agent_id}/presence",
            json={
                "status": "idle",
                "capabilities": ["reviewer"],
                "model_id": "llm-mock-v1",
                "vram_gb": 1.0,
                "ttl_sec": 60,
            },
        )
        if low.status_code != 400:
            raise RuntimeError(
                f"expected low vram_gb reviewer presence to be rejected, got {low.status_code}"
            )

        ok = client.post(
            f"{clean}/agents/{agent_id}/presence",
            json={
                "status": "idle",
                "capabilities": ["reviewer"],
                "model_id": "llm-mock-v1",
                "vram_gb": 8.0,
                "ttl_sec": 60,
            },
        )
        ok.raise_for_status()
        result["low_vram_rejected"] = "ok"

    return result


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"
    )
    expect_raw = os.environ.get("AGENTSWARM_EXPECT_HARDWARE_GATES", "").strip().lower()
    expect_enforced: bool | None = None
    if expect_raw in ("1", "true", "yes"):
        expect_enforced = True
    elif expect_raw in ("0", "false", "no"):
        expect_enforced = False

    try:
        result = verify_hardware_gates_staging(base_url, expect_enforced=expect_enforced)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Hardware gates staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Hardware gates staging OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
