"""Local web console: dispatch engineering goals and watch the role pipeline.

The console does not run volunteer workers. Post goals with create_task; execution
happens on machines running agentswarm-volunteer (or other dispatch clients).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agentswarm_agents.outcome_bundle import build_outcome_bundle
from agentswarm_agents.replay_goal import (
    build_workspace_zip,
    fetch_replay_context,
    list_workspace_tree,
    merge_trace_into_context,
    read_workspace_file,
    verify_goal_locally,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
GOAL_ID_RE = re.compile(r"goal_id=(goal-[0-9a-f]+)", re.IGNORECASE)

app = FastAPI(title="AgentSwarm Task Console", version="0.3.0")


class RunRequest(BaseModel):
    api_url: str = Field(default="https://theebie.de/agentswarm/api")
    task_file: str = Field(default="tasks/example-primes.txt")


@dataclass
class RunState:
    run_id: str
    api_url: str
    task_file: str
    status: str = "running"
    goal_id: str | None = None
    logs: list[str] = field(default_factory=list)
    exit_code: int | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _proc: subprocess.Popen[str] | None = None

    def append_log(self, line: str) -> None:
        self.logs.append(line)
        match = GOAL_ID_RE.search(line)
        if match:
            self.goal_id = match.group(1)


RUNS: dict[str, RunState] = {}
RUNS_LOCK = threading.Lock()


def _platform_auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    token = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN") or os.environ.get(
        "AGENTSWARM_OWNER_TOKEN"
    )
    if token:
        headers["X-Bootstrap-Token"] = token
    return headers


def _resolve_task_file(task_file: str) -> Path:
    path = Path(task_file)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"task file not found: {path}")
    if REPO_ROOT not in path.parents and path != REPO_ROOT:
        raise ValueError("task file must be inside the repository")
    return path


def _reader_thread(run: RunState) -> None:
    proc = run._proc
    if proc is None or proc.stdout is None:
        return
    for line in proc.stdout:
        run.append_log(line.rstrip("\n"))
    exit_code = proc.wait()
    run.exit_code = exit_code
    run.finished_at = time.time()
    run.status = "dispatched" if exit_code == 0 else "failed"


def _dispatch_run(body: RunRequest) -> RunState:
    """Enqueue a goal on the platform (no local workers)."""
    task_path = _resolve_task_file(body.task_file)
    env = os.environ.copy()
    env.setdefault("AGENTSWARM_REPO_ROOT", str(REPO_ROOT))
    env["AGENTSWARM_PLATFORM_URL"] = body.api_url.rstrip("/")
    env["AGENTSWARM_STAGING_API_URL"] = body.api_url.rstrip("/")

    cmd = [
        sys.executable,
        "-m",
        "agentswarm_agents.create_task",
        "--task-file",
        str(task_path),
        "--base-url",
        body.api_url.rstrip("/"),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    run_id = f"run-{int(time.time())}-{os.getpid()}"
    run = RunState(
        run_id=run_id,
        api_url=body.api_url.rstrip("/"),
        task_file=str(task_path.relative_to(REPO_ROOT)),
        _proc=proc,
    )
    run.append_log(f"$ {' '.join(cmd)}")
    run.append_log(
        "Goal queued on platform. Start agentswarm-volunteer on worker machine(s) to execute."
    )
    thread = threading.Thread(target=_reader_thread, args=(run,), daemon=True)
    thread.start()
    return run


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    tasks_dir = REPO_ROOT / "tasks"
    task_files = sorted(
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in tasks_dir.glob("*.txt")
    )
    return {
        "repo_root": str(REPO_ROOT),
        "default_api_url": os.environ.get(
            "AGENTSWARM_STAGING_API_URL",
            os.environ.get("AGENTSWARM_PLATFORM_URL", "https://theebie.de/agentswarm/api"),
        ),
        "task_files": task_files,
        "has_bootstrap_token": bool(os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN")),
        "has_assignment_secret": bool(os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET")),
        "dispatch_only": True,
        "docker_available": _docker_available(),
    }


def _docker_available() -> bool:
    try:
        from agentswarm_agents.sandbox_executor import docker_available

        return docker_available()
    except ImportError:
        return False


@app.post("/api/runs")
def create_run(body: RunRequest) -> dict[str, Any]:
    try:
        run = _dispatch_run(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with RUNS_LOCK:
        RUNS[run.run_id] = run
    return {
        "run_id": run.run_id,
        "status": run.status,
        "task_file": run.task_file,
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    with RUNS_LOCK:
        run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": run.run_id,
        "status": run.status,
        "goal_id": run.goal_id,
        "task_file": run.task_file,
        "api_url": run.api_url,
        "exit_code": run.exit_code,
        "logs": run.logs[-400:],
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@app.get("/api/task-files/{task_path:path}")
def read_task_file(task_path: str) -> dict[str, Any]:
    try:
        path = _resolve_task_file(task_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {"path": rel, "content": text}


@app.get("/api/proxy/dispatch/capacity")
def proxy_dispatch_capacity(api_url: str) -> dict[str, Any]:
    clean = api_url.rstrip("/")
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        response = client.get(f"{clean}/dispatch/capacity", headers=_platform_auth_headers())
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="dispatch/capacity requires bootstrap token in server env",
            )
        response.raise_for_status()
        return response.json()


@app.get("/api/proxy/creative/goals")
def proxy_list_creative_goals(
    api_url: str,
    q: str | None = None,
    status: str | None = None,
    goal_kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    clean = api_url.rstrip("/")
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if q:
        params["q"] = q
    if status:
        params["status"] = status
    if goal_kind:
        params["goal_kind"] = goal_kind
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(
            f"{clean}/creative/goals",
            params=params,
            headers=_platform_auth_headers(),
        )
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="listing goals requires bootstrap token in server env",
            )
        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="platform does not support goal listing yet — deploy latest platform API",
            )
        response.raise_for_status()
        return response.json()


@app.get("/api/proxy/goals/{goal_id}/trace")
def proxy_goal_trace(goal_id: str, api_url: str) -> dict[str, Any]:
    clean = api_url.rstrip("/")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(f"{clean}/creative/goals/{goal_id}/trace")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="goal not found")
        response.raise_for_status()
        return response.json()


@app.get("/api/proxy/goals/{goal_id}")
def proxy_goal(goal_id: str, api_url: str) -> dict[str, Any]:
    clean = api_url.rstrip("/")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(f"{clean}/creative/goals/{goal_id}")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="goal not found")
        response.raise_for_status()
        return response.json()


class ReplayRequest(BaseModel):
    api_url: str = Field(default="https://theebie.de/agentswarm/api")


def _load_replay_context(api_url: str, goal_id: str) -> dict[str, Any]:
    clean = api_url.rstrip("/")
    ctx = fetch_replay_context(clean, goal_id)
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            trace_response = client.get(f"{clean}/creative/goals/{goal_id}/trace")
            trace = trace_response.json() if trace_response.status_code == 200 else None
    except httpx.HTTPError:
        trace = None
    return merge_trace_into_context(ctx, trace)


@app.get("/api/proxy/goals/{goal_id}/replay-context")
def proxy_replay_context(goal_id: str, api_url: str) -> dict[str, Any]:
    try:
        return fetch_replay_context(api_url.rstrip("/"), goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/goals/{goal_id}/outcome")
def goal_outcome(goal_id: str, api_url: str) -> dict[str, Any]:
    try:
        ctx = _load_replay_context(api_url, goal_id)
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            trace_response = client.get(f"{api_url.rstrip('/')}/creative/goals/{goal_id}/trace")
        if trace_response.status_code == 404:
            raise HTTPException(status_code=404, detail="goal not found")
        trace_response.raise_for_status()
        trace = trace_response.json()
        return build_outcome_bundle(trace, replay_context=ctx)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/goals/{goal_id}/workspace-tree")
def goal_workspace_tree(goal_id: str, api_url: str) -> dict[str, Any]:
    try:
        ctx = _load_replay_context(api_url, goal_id)
        return list_workspace_tree(ctx)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/goals/{goal_id}/workspace-file")
def goal_workspace_file(goal_id: str, api_url: str, path: str) -> dict[str, Any]:
    try:
        ctx = _load_replay_context(api_url, goal_id)
        return read_workspace_file(ctx, path=path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/goals/{goal_id}/verify-locally")
def goal_verify_locally(goal_id: str, body: ReplayRequest) -> dict[str, Any]:
    try:
        ctx = _load_replay_context(body.api_url, goal_id)
        return verify_goal_locally(ctx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/goals/{goal_id}/workspace-zip")
def goal_workspace_zip(goal_id: str, api_url: str) -> Response:
    try:
        ctx = _load_replay_context(api_url, goal_id)
        data, filename = build_workspace_zip(ctx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/proxy/artifacts/{artifact_ref:path}")
def proxy_artifact(artifact_ref: str, api_url: str) -> dict[str, Any]:
    clean = api_url.rstrip("/")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(
            f"{clean}/artifacts/{artifact_ref}",
            headers=_platform_auth_headers(),
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="artifact not found")
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="artifact fetch requires bootstrap token in server env",
            )
        response.raise_for_status()
        return response.json()


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    import uvicorn

    port = int(os.environ.get("AGENTSWARM_TASK_CONSOLE_PORT", "8765"))
    uvicorn.run(
        "tools.task_console.server:app",
        host="127.0.0.1",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
