#!/usr/bin/env python3
"""Verify theebie.de staging platform API health and dispatch mode."""

from __future__ import annotations

import os
import sys

import httpx


def verify_staging_api(base_url: str, *, timeout: float = 30.0) -> dict[str, str]:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("staging API URL must start with https://")

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        health = client.get(f"{clean}/health")
        health.raise_for_status()
        body = health.json()
        if body != {"status": "ok"}:
            raise RuntimeError(f"unexpected /health body: {body!r}")

        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        cfg = config.json()
        mode = cfg.get("assignment_mode")
        if mode != "dispatch":
            raise RuntimeError(f"expected assignment_mode=dispatch, got {mode!r}")

    return {"health": "ok", "assignment_mode": str(mode)}


def main() -> int:
    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api")
    )
    try:
        result = verify_staging_api(url)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Staging API verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Staging API OK: {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
