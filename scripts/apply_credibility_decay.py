#!/usr/bin/env python3
"""Apply credibility inactivity decay across all balances (maintainer cron helper)."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

from agentswarm_sdk import PlatformClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--project-id")
    args = parser.parse_args()

    params = {}
    if args.project_id:
        params["project_id"] = args.project_id

    with PlatformClient(args.base_url) as platform:
        response = platform._http.post(
            "/credibility/apply-decay",
            params=params,
            headers=platform._owner_headers(),
        )
    if response.status_code != 200:
        print(response.text, file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
