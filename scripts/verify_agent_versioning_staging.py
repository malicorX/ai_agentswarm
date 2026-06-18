#!/usr/bin/env python3
"""Verify agent versioning on a public staging platform (P5.7 / P5.8)."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

from agentswarm_agents.identity import connect_agent
from verify_http_retry import retry_transient


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def verify_agent_versioning_staging(base_url: str, *, timeout: float = 30.0) -> dict[str, str]:
    clean = _clean_url(base_url)
    agent_name = f"version-verify-{uuid.uuid4().hex[:8]}"
    result: dict[str, str] = {"platform_url": clean, "agent_name": agent_name}

    override_dir = os.environ.get("AGENTSWARM_VERSION_VERIFY_IDENTITY_DIR", "")
    temp_identity: tempfile.TemporaryDirectory[str] | None = None
    if override_dir:
        identity_dir = Path(override_dir)
        identity_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_identity = tempfile.TemporaryDirectory(prefix="agentswarm-version-verify-")
        identity_dir = Path(temp_identity.name)
    os.environ["AGENTSWARM_IDENTITY_DIR"] = str(identity_dir)

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        health = client.get(f"{clean}/health")
        health.raise_for_status()
        if health.json() != {"status": "ok"}:
            raise RuntimeError(f"unexpected /health body: {health.json()!r}")
        result["health"] = "ok"

        first = retry_transient(
            lambda: connect_agent(
                agent_name=agent_name,
                owner="version-verify",
                capabilities=["reviewer"],
                base_url=clean,
                version_signature="reviewer-v1.0",
            ),
            label="initial agent register",
        )
        agent_id = first.agent_id
        result["agent_id"] = agent_id

        versions_resp = client.get(f"{clean}/agents/{agent_id}/versions")
        versions_resp.raise_for_status()
        versions = versions_resp.json().get("versions")
        if not isinstance(versions, list):
            raise RuntimeError("unexpected /versions response shape")
        if len(versions) != 1 or versions[0].get("bump_kind") != "initial":
            raise RuntimeError(f"expected one initial version entry, got {versions!r}")
        result["initial"] = versions[0]["version_signature"]

        second = retry_transient(
            lambda: connect_agent(
                agent_name=agent_name,
                owner="version-verify",
                capabilities=["reviewer"],
                base_url=clean,
                version_signature="reviewer-v1.1",
            ),
            label="minor version register",
        )
        if second.agent_id != agent_id:
            raise RuntimeError("reconnect changed agent_id after minor bump")

        versions_resp = client.get(f"{clean}/agents/{agent_id}/versions")
        versions_resp.raise_for_status()
        versions = versions_resp.json()["versions"]
        if len(versions) != 2:
            raise RuntimeError(f"expected two version entries after minor bump, got {len(versions)}")
        last = versions[-1]
        if last.get("bump_kind") != "minor":
            raise RuntimeError(f"expected minor bump_kind, got {last!r}")
        if last.get("previous_version") != "reviewer-v1.0":
            raise RuntimeError(f"unexpected previous_version: {last.get('previous_version')!r}")
        result["minor_bump"] = last["version_signature"]

        third = retry_transient(
            lambda: connect_agent(
                agent_name=agent_name,
                owner="version-verify",
                capabilities=["reviewer"],
                base_url=clean,
                version_signature="reviewer-v2.0",
            ),
            label="major version register",
        )
        if third.agent_id != agent_id:
            raise RuntimeError("reconnect changed agent_id after major bump")

        versions_resp = client.get(f"{clean}/agents/{agent_id}/versions")
        versions_resp.raise_for_status()
        versions = versions_resp.json()["versions"]
        if len(versions) != 3:
            raise RuntimeError(f"expected three version entries after major bump, got {len(versions)}")
        last = versions[-1]
        if last.get("bump_kind") != "major":
            raise RuntimeError(f"expected major bump_kind, got {last!r}")
        result["major_bump"] = last["version_signature"]

    if temp_identity is not None:
        temp_identity.cleanup()

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
        result = verify_agent_versioning_staging(url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Agent versioning staging verify failed: {exc}", file=sys.stderr)
        return 1

    print(f"Agent versioning staging OK: {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
