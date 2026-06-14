from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.identity import connect_agent


def repo_root() -> Path:
    env = os.environ.get("AGENTSWARM_REPO_ROOT", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4]


def run_deploy_hooks(request: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    hook_env = os.environ.copy()
    artifact_ref = str(request.get("artifact_ref", "")).strip()
    if artifact_ref:
        hook_env["AGENTSWARM_DEPLOY_ARTIFACT_REF"] = artifact_ref

    staging_flag = os.environ.get("AGENTSWARM_DEPLOY_STAGING", "").lower()
    if staging_flag in ("1", "true", "yes"):
        script = repo_root() / "scripts" / "stage_pilot_site.py"
        output = os.environ.get("AGENTSWARM_PILOT_STAGING_DIR", "").strip()
        cmd = [sys.executable, str(script)]
        if output:
            cmd.extend(["--output", output])
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root(),
            env=hook_env,
        )
        staging_dir = proc.stdout.strip().splitlines()[-1]
        details["staging_dir"] = staging_dir
        details["hook"] = "stage_pilot_site"

    hook_cmd = os.environ.get("AGENTSWARM_DEPLOY_HOOK", "").strip()
    if hook_cmd:
        proc = subprocess.run(
            hook_cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=repo_root(),
            env=hook_env,
        )
        details["hook_command"] = hook_cmd
        details["hook_exit_code"] = proc.returncode
        if proc.stdout:
            details["hook_stdout"] = proc.stdout[-500:]
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "deploy hook failed")

    target = os.environ.get("AGENTSWARM_DEPLOY_TARGET_URL", "").strip()
    if target:
        details["target_url"] = target

    return details


def build_execution_result(
    request: dict[str, Any],
    *,
    hook_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hook_details = hook_details or {}
    outcome = "simulated"
    message = "Deploy execution recorded (set AGENTSWARM_DEPLOY_STAGING=1 to stage pilot)"
    if hook_details.get("staging_dir"):
        outcome = "staged"
        message = f"Pilot staged at {hook_details['staging_dir']}"
    elif hook_details.get("hook_command"):
        outcome = "hook_ran"
        message = "Custom deploy hook completed"
    elif hook_details.get("target_url"):
        outcome = "target_configured"
        message = f"Deploy target configured: {hook_details['target_url']}"

    result = {
        "request_id": request["request_id"],
        "environment": request["environment"],
        "artifact_ref": request["artifact_ref"],
        "outcome": outcome,
        "message": message,
    }
    result.update(hook_details)
    return result


def fetch_deploy_request(base_url: str, request_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/deploy/requests/{request_id}",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def execute_deploy(base_url: str, request_id: str) -> dict[str, Any]:
    request = fetch_deploy_request(base_url, request_id)
    if request["status"] not in ("approved", "deployed"):
        raise ValueError(f"deploy request {request_id} is {request['status']}")
    hook_details = run_deploy_hooks(request)
    return build_execution_result(request, hook_details=hook_details)


def run_once(client, base_url: str) -> bool:
    tasks = client.poll_tasks(capability="deployer")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    request_id = task.get("payload", {}).get("request_id")
    if not request_id:
        raise ValueError("deploy.execute task missing request_id")
    result = execute_deploy(base_url, str(request_id))
    client.submit(claim_token, task["task_id"], result)
    print(
        f"deployer: completed {task['task_id']} for {request_id} "
        f"({result['outcome']})"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm deployer agent")
    parser.add_argument("--agent-name", default="deployer")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    base_url = platform_url()
    client = connect_agent(
        agent_name=args.agent_name,
        owner="phase3-deployer",
        capabilities=["deployer"],
        base_url=base_url,
    )
    print(f"deployer: connected as {client.agent_id}")
    if args.once:
        if not run_once(client, base_url):
            print("deployer: no tasks")
        return
    while True:
        if run_once(client, base_url):
            continue
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
