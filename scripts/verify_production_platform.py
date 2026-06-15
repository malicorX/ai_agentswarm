#!/usr/bin/env python3
"""Verify a public AgentSwarm platform URL (P5.0 production checklist)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_platform.crypto import generate_keypair, public_key_b64


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


def verify_production_platform(
    base_url: str,
    *,
    timeout: float = 30.0,
    expect_dispatch: bool | None = None,
    register_smoke: bool = True,
) -> dict[str, str]:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")

    result: dict[str, str] = {}

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        health = client.get(f"{clean}/health")
        health.raise_for_status()
        body = health.json()
        if body != {"status": "ok"}:
            raise RuntimeError(f"unexpected /health body: {body!r}")
        result["health"] = "ok"

        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        config_body = config.json()
        mode = config_body.get("assignment_mode")
        if mode not in ("pull", "dispatch"):
            raise RuntimeError(f"unexpected assignment_mode: {mode!r}")
        result["assignment_mode"] = str(mode)
        auth_block = config_body.get("auth")
        if isinstance(auth_block, dict):
            result["auth_enforced"] = str(bool(auth_block.get("enforced")))
        if expect_dispatch is True and mode != "dispatch":
            raise RuntimeError(f"expected assignment_mode=dispatch, got {mode!r}")
        if expect_dispatch is False and mode != "pull":
            raise RuntimeError(f"expected assignment_mode=pull, got {mode!r}")

        if register_smoke:
            pub, _priv = generate_keypair()
            agent_name = f"verify-{uuid.uuid4().hex[:8]}"
            reg = client.post(
                f"{clean}/agents/register",
                json={
                    "public_key": public_key_b64(pub),
                    "owner": agent_name,
                    "capabilities": ["reviewer"],
                },
                headers=_register_headers(config_body),
            )
            reg.raise_for_status()
            agent_id = reg.json().get("agent_id")
            if not agent_id:
                raise RuntimeError("register response missing agent_id")
            result["register"] = str(agent_id)
            result["agent_name"] = agent_name

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
    expect_dispatch: bool | None = None
    if os.environ.get("AGENTSWARM_EXPECT_DISPATCH", "").lower() in ("1", "true", "yes"):
        expect_dispatch = True

    try:
        result = verify_production_platform(url, expect_dispatch=expect_dispatch)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Production platform verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Production platform OK: {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
