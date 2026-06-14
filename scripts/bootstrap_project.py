#!/usr/bin/env python3
"""Create an AgentSwarm project from a governance template."""

from __future__ import annotations

import argparse
import json
import os
import sys

from agentswarm_sdk import PlatformClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTSWARM_PLATFORM_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--template", default="minimal")
    parser.add_argument("--description")
    args = parser.parse_args()

    platform = PlatformClient(
        args.base_url,
        bootstrap_token=os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN"),
        owner_token=os.environ.get("AGENTSWARM_OWNER_TOKEN"),
    )
    try:
        project = platform.create_project(
            args.name,
            project_id=args.project_id,
            description=args.description,
            governance_template_id=args.template,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        platform.close()

    print(json.dumps(project, indent=2))


if __name__ == "__main__":
    main()
