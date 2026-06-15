#!/usr/bin/env python3
"""Verify volunteer model allowlist enforcement on staging (P8.0)."""

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


def verify_model_allowlist_staging(
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
        models_block = config_body.get("models")
        if not isinstance(models_block, dict):
            raise RuntimeError("platform config missing models block")
        enforced = bool(models_block.get("enforced"))
        result["models_enforced"] = str(enforced)
        allowlist = models_block.get("allowlist")
        if not isinstance(allowlist, list) or not allowlist:
            raise RuntimeError("platform config missing models.allowlist")

        if expect_enforced is True and not enforced:
            raise RuntimeError("expected models.enforced=true on platform")
        if expect_enforced is False and enforced:
            raise RuntimeError("expected models.enforced=false on platform")

        headers = _register_headers(config_body)
        pub, _priv = generate_keypair()
        reg = client.post(
            f"{clean}/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"model-verify-{uuid.uuid4().hex[:8]}",
                "capabilities": ["reviewer"],
            },
            headers=headers,
        )
        reg.raise_for_status()
        agent_id = reg.json().get("agent_id")
        if not agent_id:
            raise RuntimeError("register response missing agent_id")
        result["register"] = str(agent_id)

        bad = client.post(
            f"{clean}/agents/{agent_id}/presence",
            json={
                "status": "idle",
                "capabilities": ["reviewer"],
                "model_id": "not-on-allowlist",
                "ttl_sec": 60,
            },
        )
        if enforced:
            if bad.status_code != 400:
                raise RuntimeError(
                    f"expected 400 for unknown model_id, got {bad.status_code}: {bad.text}"
                )
            result["unknown_model_presence"] = "rejected"
        else:
            if bad.status_code == 400:
                result["unknown_model_presence"] = "rejected_unexpected"
            else:
                bad.raise_for_status()
                result["unknown_model_presence"] = "accepted"

        allowed_payload: dict[str, object] = {
            "status": "idle",
            "capabilities": ["reviewer"],
            "model_id": "llm-mock-v1",
            "ttl_sec": 60,
        }
        hardware_block = config_body.get("hardware")
        if isinstance(hardware_block, dict) and hardware_block.get("enforced"):
            min_vram = float(hardware_block.get("reviewer_min_vram_gb", 6.0))
            allowed_payload["vram_gb"] = max(8.0, min_vram)
            result["hardware_gates"] = "enforced"

        good = client.post(
            f"{clean}/agents/{agent_id}/presence",
            json=allowed_payload,
        )
        good.raise_for_status()
        result["allowed_model_presence"] = "ok"

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
    expect_enforced: bool | None = None
    if os.environ.get("AGENTSWARM_EXPECT_MODEL_ALLOWLIST", "").lower() in ("1", "true", "yes"):
        expect_enforced = True
    if os.environ.get("AGENTSWARM_EXPECT_OPEN_MODEL_ALLOWLIST", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        expect_enforced = False

    try:
        outcome = verify_model_allowlist_staging(url, expect_enforced=expect_enforced)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Model allowlist staging verify failed: {exc}", file=sys.stderr)
        return 1

    print(f"Model allowlist staging OK: {url.strip().rstrip('/')} ({outcome})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
