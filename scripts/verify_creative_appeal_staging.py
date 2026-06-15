#!/usr/bin/env python3
"""Live smoke for creative goal appeal routes (P7.3 / P7.4 staging bundle)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))

from agentswarm_agents.owner_auth import owner_auth_headers


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def verify_creative_appeal_staging(base_url: str, *, timeout: float = 30.0) -> dict[str, str]:
    """Prove appeal endpoints are wired on a live staging platform."""
    clean = _clean_url(base_url)
    headers = owner_auth_headers()
    if not headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN for appeal verify"
        )

    fake_goal = f"goal-verify-{uuid.uuid4().hex}"
    result: dict[str, str] = {"platform_url": clean, "probe_goal_id": fake_goal}

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        missing = client.get(f"{clean}/creative/goals/{fake_goal}")
        if missing.status_code != 404:
            raise RuntimeError(f"expected 404 for missing goal, got {missing.status_code}")
        result["get_missing_goal"] = "404"

        appeal_body: dict[str, Any] = {
            "filed_by_agent_id": "agent-probe",
            "message": "P7.4 staging verify — appeal route smoke.",
        }
        appeal = client.post(
            f"{clean}/creative/goals/{fake_goal}/appeal",
            json=appeal_body,
            headers=headers,
        )
        if appeal.status_code != 400:
            raise RuntimeError(
                f"expected 400 for appeal on missing goal, got {appeal.status_code}: {appeal.text}"
            )
        result["post_appeal_missing_goal"] = "400"

        resolve = client.post(
            f"{clean}/creative/goals/{fake_goal}/appeal/resolve",
            json={"decision": "uphold", "resolution_note": "staging verify"},
            headers=headers,
        )
        if resolve.status_code != 400:
            raise RuntimeError(
                f"expected 400 for resolve on missing goal, got {resolve.status_code}: {resolve.text}"
            )
        result["post_resolve_missing_goal"] = "400"

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
        outcome = verify_creative_appeal_staging(url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Creative appeal staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Creative appeal staging OK: {url.strip().rstrip('/')} ({outcome})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
