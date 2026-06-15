#!/usr/bin/env python3
"""Verify registration auth behavior (P5.11 production hardening)."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_platform.crypto import generate_keypair, public_key_b64

_AUTH_TESTS = _ROOT / "platform" / "tests" / "test_auth.py"


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def verify_registration_auth_staging(
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
        auth_block = config.json().get("auth")
        if not isinstance(auth_block, dict):
            raise RuntimeError("platform config missing auth block")
        enforced = bool(auth_block.get("enforced"))
        result["auth_enforced"] = str(enforced)
        result["open_registration"] = str(bool(auth_block.get("open_registration")))

        if expect_enforced is True and not enforced:
            raise RuntimeError("expected auth.enforced=true on platform")
        if expect_enforced is False and enforced:
            raise RuntimeError("expected auth.enforced=false on platform")

        pub, _priv = generate_keypair()
        anonymous = client.post(
            f"{clean}/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"anon-{uuid.uuid4().hex[:8]}",
                "capabilities": ["reviewer"],
            },
        )
        if enforced:
            if anonymous.status_code != 401:
                raise RuntimeError(
                    f"expected 401 for unauthenticated register, got {anonymous.status_code}"
                )
            result["anonymous_register"] = "rejected"
            bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip()
            if not bootstrap:
                raise RuntimeError(
                    "auth enforced; set AGENTSWARM_BOOTSTRAP_TOKEN to complete verify"
                )
            authed = client.post(
                f"{clean}/agents/register",
                json={
                    "public_key": public_key_b64(generate_keypair()[0]),
                    "owner": f"bootstrap-{uuid.uuid4().hex[:8]}",
                    "capabilities": ["reviewer"],
                },
                headers={"X-Bootstrap-Token": bootstrap},
            )
            authed.raise_for_status()
            result["bootstrap_register"] = authed.json().get("agent_id", "ok")
        else:
            if anonymous.status_code != 200:
                raise RuntimeError(
                    f"expected open registration, got {anonymous.status_code}: "
                    f"{anonymous.text}"
                )
            result["anonymous_register"] = "allowed"

    return result


def main() -> int:
    if not _AUTH_TESTS.is_file():
        print(f"Missing {_AUTH_TESTS}", file=sys.stderr)
        return 1

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(_AUTH_TESTS), "-q"],
        cwd=_ROOT,
        check=False,
    )
    if proc.returncode != 0:
        print("Registration auth unit tests failed", file=sys.stderr)
        return proc.returncode

    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", ""),
        )
    )
    if not url.strip():
        print("Registration auth unit tests OK")
        return 0

    expect_enforced: bool | None = None
    if os.environ.get("AGENTSWARM_EXPECT_REGISTRATION_AUTH", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        expect_enforced = True
    if os.environ.get("AGENTSWARM_EXPECT_OPEN_REGISTRATION", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        expect_enforced = False

    try:
        result = verify_registration_auth_staging(url, expect_enforced=expect_enforced)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Registration auth staging verify failed: {exc}", file=sys.stderr)
        return 1

    print(f"Registration auth OK: {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
