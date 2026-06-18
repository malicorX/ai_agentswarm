#!/usr/bin/env python3
"""Verify verified-goal → deploy-request bridge on staging (D5)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_agents.owner_auth import owner_auth_headers
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


def verify_goal_deploy_staging(
    base_url: str,
    *,
    timeout: float = 30.0,
) -> dict[str, str]:
    """Ensure deploy-from-goal endpoint exists and rejects unverified goals."""
    clean = _clean_url(base_url)
    owner_headers = owner_auth_headers()
    if not owner_headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN for goal deploy verify"
        )

    result: dict[str, str] = {"platform_url": clean}

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        reg_headers = _register_headers(config.json())

        pub, _priv = generate_keypair()
        suffix = uuid.uuid4().hex[:8]
        reg = client.post(
            f"{clean}/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"goal-deploy-verify-{suffix}",
                "capabilities": ["codewriter"],
            },
            headers=reg_headers,
        )
        reg.raise_for_status()
        poster_id = reg.json()["agent_id"]

        goal = client.post(
            f"{clean}/creative/goals",
            json={
                "poster_agent_id": poster_id,
                "brief": "goal deploy verify pending",
                "rubric": [{"id": "quality", "weight": 1.0}],
                "goal_kind": "engineering",
                "verification_spec": {"fixture": "primes", "lab": "engineering-lab"},
                "min_reviewers": 1,
            },
            headers=owner_headers,
        )
        if goal.status_code == 400 and "dispatch" in goal.text.lower():
            result["deploy_from_goal"] = "skipped_no_dispatch"
            return result
        goal.raise_for_status()
        goal_id = goal.json()["goal_id"]
        result["goal_id"] = goal_id

        blocked = client.post(
            f"{clean}/creative/goals/{goal_id}/deploy-request",
            headers=owner_headers,
            json={"environment": "staging", "artifact_ref": "sha256:" + "0" * 64},
        )
        if blocked.status_code == 404:
            result["deploy_from_goal"] = "skipped_not_deployed"
            return result
        if blocked.status_code != 400:
            raise RuntimeError(
                f"expected deploy-request on pending goal to return 400, got {blocked.status_code}"
            )
        if "verified" not in blocked.text.lower():
            raise RuntimeError(
                f"expected verified goal error, got: {blocked.text[:200]}"
            )
        result["unverified_rejected"] = "ok"

        missing = client.post(
            f"{clean}/creative/goals/goal-nonexistent/deploy-request",
            headers=owner_headers,
            json={"environment": "staging", "artifact_ref": "v0.0.0"},
        )
        if missing.status_code not in (400, 404):
            raise RuntimeError(
                f"expected missing goal deploy-request to fail, got {missing.status_code}"
            )
        result["missing_goal_rejected"] = "ok"

    result["deploy_from_goal"] = "ok"
    return result


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"
    )
    try:
        result = verify_goal_deploy_staging(base_url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Goal deploy staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Goal deploy staging OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
