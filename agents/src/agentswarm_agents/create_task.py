"""Enqueue a task on the platform without starting volunteer workers."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.engineering_workspace import resolve_engineering_git_workspace
from agentswarm_agents.task_file import TaskSpec, load_task_file, validate_task_spec
from agentswarm_agents.volunteer_team import clean_platform_url, goal_auth_headers
from agentswarm_platform.crypto import generate_keypair, public_key_b64


def register_poster_agent(base_url: str, *, timeout: float = 30.0) -> str:
    clean = clean_platform_url(base_url)
    headers = goal_auth_headers()
    if not headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN to create tasks"
        )
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        pub, _priv = generate_keypair()
        suffix = uuid.uuid4().hex[:8]
        reg = client.post(
            f"{clean}/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": f"task-poster-{suffix}",
                "capabilities": ["codewriter"],
            },
            headers=headers,
        )
        reg.raise_for_status()
        poster_id = reg.json()["agent_id"]
        if not poster_id:
            raise RuntimeError("agent registration missing agent_id")
        return poster_id


def create_goal_from_spec(
    base_url: str,
    spec: TaskSpec,
    *,
    poster_agent_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    validate_task_spec(spec)
    clean = clean_platform_url(base_url)
    headers = goal_auth_headers()
    if not headers:
        raise RuntimeError(
            "set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN to create tasks"
        )

    poster_id = poster_agent_id or register_poster_agent(clean, timeout=timeout)
    payload = spec.goal_payload_fields()
    payload["poster_agent_id"] = poster_id
    if spec.goal_kind == "engineering" and spec.workspace_mode == "git":
        payload["workspace"] = resolve_engineering_git_workspace(
            fixture=spec.fixture,
            workspace_repo_url=spec.workspace_repo_url,
        )

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.post(f"{clean}/creative/goals", json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()

    goal_id = body.get("goal_id")
    coordinator_task_id = body.get("coordinator_task_id")
    if not goal_id or not coordinator_task_id:
        raise RuntimeError("creative goal response missing goal_id or coordinator_task_id")

    return {
        "platform_url": clean,
        "poster_agent_id": poster_id,
        "goal_id": goal_id,
        "coordinator_task_id": coordinator_task_id,
        "status": body.get("status", "pending"),
        "goal_kind": spec.goal_kind,
        "brief": spec.brief,
        "verification_spec": spec.verification_spec(),
        "project_id": spec.project_id,
    }


def create_task_from_file(
    base_url: str,
    task_file: str | Path,
) -> dict[str, Any]:
    spec = load_task_file(task_file)
    return create_goal_from_spec(base_url, spec)


def format_create_task_output(result: dict[str, Any]) -> str:
    lines = [
        f"goal_id={result['goal_id']}",
        f"coordinator_task_id={result['coordinator_task_id']}",
        f"TaskId={result['goal_id']}",
        f"initial_status={result.get('status', 'pending')}",
        "note=live status updates on the platform when volunteers finish (watch goal trace)",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentswarm-create-task",
        description="Enqueue a task file on the platform task pool (no local workers).",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", platform_url()),
        ),
    )
    parser.add_argument(
        "--task-file",
        required=True,
        help="Path to task definition file (optional YAML frontmatter + brief body)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = create_task_from_file(args.base_url, args.task_file)
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        print(f"create_task failed: {exc}", file=sys.stderr)
        return 1
    print(format_create_task_output(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
