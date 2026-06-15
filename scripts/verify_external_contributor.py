#!/usr/bin/env python3
"""Verify external contributor quickstart against a public platform (P5.3)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_agents.identity import connect_agent, identity_path, load_identity
from agentswarm_agents.owner_auth import owner_auth_headers


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def _enqueue_add_article(
    client: httpx.Client,
    base_url: str,
    *,
    article_id: str,
) -> str:
    body: dict[str, Any] = {
        "task_type": "codewriter.add-article",
        "capability_required": "codewriter",
        "payload": {
            "article": {
                "id": article_id,
                "title": "External contributor trial",
                "summary": "P5.3 verify script — remote agent add-article.",
                "url": "https://example.com/external-contributor-trial",
                "source": "P5.3 verify",
                "published_at": "2026-06-15T12:00:00+00:00",
                "topics": ["external-trial"],
            }
        },
    }
    response = client.post(
        f"{base_url}/tasks",
        json=body,
        headers=owner_auth_headers(),
    )
    response.raise_for_status()
    task_id = response.json().get("task_id")
    if not task_id:
        raise RuntimeError("enqueue response missing task_id")
    return str(task_id)


def _wait_task_progress(
    client: httpx.Client,
    base_url: str,
    task_id: str,
    *,
    timeout: float,
    poll_interval: float,
) -> str:
    deadline = time.monotonic() + timeout
    last_status = "unknown"
    while time.monotonic() < deadline:
        response = client.get(f"{base_url}/tasks/{task_id}")
        response.raise_for_status()
        last_status = str(response.json().get("status", "unknown"))
        if last_status in ("submitted", "verified"):
            return last_status
        time.sleep(poll_interval)
    raise RuntimeError(
        f"task {task_id} did not reach submitted/verified within {timeout}s (last={last_status})"
    )


def _run_codewriter_once(
    *,
    repo_root: Path,
    identity_dir: Path,
    platform_url: str,
    agent_name: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTSWARM_PLATFORM_URL"] = platform_url
    env["AGENTSWARM_IDENTITY_DIR"] = str(identity_dir)
    env["AGENTSWARM_REPO_ROOT"] = str(repo_root)
    # Drop owner JWT so the subprocess behaves like an external machine; keep bootstrap
    # when auth is enforced — invited contributors register with X-Bootstrap-Token.
    env.pop("AGENTSWARM_OWNER_TOKEN", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agentswarm_agents.workers.codewriter",
            "--once",
            "--agent-name",
            agent_name,
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def verify_external_contributor(
    base_url: str,
    *,
    repo_root: Path | None = None,
    identity_dir: Path | None = None,
    bootstrap_token: str | None = None,
    run_task_flow: bool = True,
    task_timeout: float = 120.0,
    poll_interval: float = 2.0,
    codewriter_attempts: int = 8,
) -> dict[str, str]:
    """Simulate a non-maintainer machine running the external agent quickstart."""
    clean = _clean_url(base_url)
    root = repo_root or _ROOT
    if not (root / "pilot" / "news-hub").is_dir():
        raise ValueError(f"pilot checkout not found under {root}")

    temp_identity: tempfile.TemporaryDirectory[str] | None = None
    if identity_dir is None:
        temp_identity = tempfile.TemporaryDirectory(prefix="agentswarm-external-")
        identity_dir = Path(temp_identity.name)

    agent_name = f"external-trial-{uuid.uuid4().hex[:8]}"
    result: dict[str, str] = {"platform_url": clean, "agent_name": agent_name}
    identity_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AGENTSWARM_IDENTITY_DIR"] = str(identity_dir)

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        health = client.get(f"{clean}/health")
        health.raise_for_status()
        if health.json() != {"status": "ok"}:
            raise RuntimeError(f"unexpected /health body: {health.json()!r}")
        result["health"] = "ok"

        first = connect_agent(
            agent_name=agent_name,
            owner="external-contributor",
            capabilities=["codewriter"],
            base_url=clean,
        )
        result["agent_id"] = first.agent_id

        second = connect_agent(
            agent_name=agent_name,
            owner="external-contributor",
            capabilities=["codewriter"],
            base_url=clean,
        )
        if second.agent_id != first.agent_id:
            raise RuntimeError(
                f"identity not persistent: {first.agent_id} != {second.agent_id}"
            )
        result["identity_persistence"] = "ok"

        stored = load_identity(agent_name)
        if stored is None or stored.agent_id != first.agent_id:
            raise RuntimeError("identity file missing or mismatched after connect")
        result["identity_file"] = str(identity_path(agent_name))

        poll = client.get(
            f"{clean}/tasks/poll",
            params={"agent_id": first.agent_id, "capability": "codewriter"},
        )
        poll.raise_for_status()
        if not isinstance(poll.json(), list):
            raise RuntimeError("unexpected /tasks/poll response")
        result["poll"] = "ok"

        token = bootstrap_token or os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "")
        if not run_task_flow:
            result["task_flow"] = "skipped"
            return result
        if not token:
            result["task_flow"] = "skipped_no_bootstrap"
            return result

        os.environ["AGENTSWARM_BOOTSTRAP_TOKEN"] = token
        article_id = f"external-trial-{uuid.uuid4().hex[:10]}"
        task_id = _enqueue_add_article(client, clean, article_id=article_id)
        result["enqueued_task_id"] = task_id
        result["article_id"] = article_id

        completed = False
        for attempt in range(codewriter_attempts):
            proc = _run_codewriter_once(
                repo_root=root,
                identity_dir=identity_dir,
                platform_url=clean,
                agent_name=agent_name,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    "codewriter --once failed:\n"
                    f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
                )
            if "completed" in proc.stdout:
                completed = True
                result["codewriter_cli"] = f"completed attempt {attempt + 1}"
                break
            time.sleep(poll_interval)

        if not completed:
            result["codewriter_cli"] = "no_task_claimed"

        final_status = _wait_task_progress(
            client,
            clean,
            task_id,
            timeout=task_timeout,
            poll_interval=poll_interval,
        )
        result["task_status"] = final_status
        if final_status not in ("submitted", "verified"):
            raise RuntimeError(f"unexpected final task status: {final_status}")
        result["task_flow"] = "ok"

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
    skip_task = os.environ.get("AGENTSWARM_EXTERNAL_SKIP_TASK", "").lower() in (
        "1",
        "true",
        "yes",
    )

    try:
        result = verify_external_contributor(url, run_task_flow=not skip_task)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"External contributor verify failed: {exc}", file=sys.stderr)
        return 1

    print(f"External contributor OK: {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
