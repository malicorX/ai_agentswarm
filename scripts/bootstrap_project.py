#!/usr/bin/env python3
"""Create an AgentSwarm project from a governance template."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def auth_headers() -> dict[str, str]:
    token = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN")
    if token:
        return {"X-Bootstrap-Token": token}
    owner = os.environ.get("AGENTSWARM_OWNER_TOKEN")
    if owner:
        return {"Authorization": f"Bearer {owner}"}
    raise SystemExit(
        "Set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN for project creation."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--name", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--template", default="minimal")
    parser.add_argument("--description")
    args = parser.parse_args()

    payload: dict[str, str] = {
        "name": args.name,
        "governance_template_id": args.template,
    }
    if args.project_id:
        payload["project_id"] = args.project_id
    if args.description:
        payload["description"] = args.description

    response = httpx.post(
        f"{args.base_url.rstrip('/')}/projects",
        headers=auth_headers(),
        json=payload,
        timeout=30.0,
    )
    if response.status_code != 200:
        print(response.text, file=sys.stderr)
        raise SystemExit(response.status_code)
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
