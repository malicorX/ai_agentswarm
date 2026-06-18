"""Local web console: start engineering tasks and watch the role pipeline."""

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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
GOAL_ID_RE = re.compile(r"goal_id=(goal-[0-9a-f]+)", re.IGNORECASE)

app = FastAPI(title="AgentSwarm Task Console", version="0.1.0")


class RunRequest(BaseModel):
    api_url: str = Field(default="https://theebie.de/agentswarm/api")
    task_file: str = Field(default="tasks/example-primes.txt")
    goal_timeout_sec: float = Field(default=300.0, ge=30.0, le=3600.0)


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
    run.status = "verified" if exit_code == 0 else "failed"


def _start_run(body: RunRequest) -> RunState:
    task_path = _resolve_task_file(body.task_file)
    env = os.environ.copy()
    env.setdefault("AGENTSWARM_REPO_ROOT", str(REPO_ROOT))
    env["AGENTSWARM_PLATFORM_URL"] = body.api_url.rstrip("/")
    env["AGENTSWARM_STAGING_API_URL"] = body.api_url.rstrip("/")

    cmd = [
        sys.executable,
        "-m",
        "agentswarm_agents.start_task",
        "--task-file",
        str(task_path),
        "--base-url",
        body.api_url.rstrip("/"),
        "--goal-timeout-sec",
        str(body.goal_timeout_sec),
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
    }


@app.post("/api/runs")
def create_run(body: RunRequest) -> dict[str, Any]:
    try:
        run = _start_run(body)
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
    headers: dict[str, str] = {}
    token = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN") or os.environ.get(
        "AGENTSWARM_OWNER_TOKEN"
    )
    if token:
        headers["X-Bootstrap-Token"] = token
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        response = client.get(f"{clean}/dispatch/capacity", headers=headers)
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="dispatch/capacity requires bootstrap token in server env",
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


@app.get("/api/proxy/artifacts/{artifact_ref:path}")
def proxy_artifact(artifact_ref: str, api_url: str) -> dict[str, Any]:
    clean = api_url.rstrip("/")
    headers: dict[str, str] = {}
    token = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN") or os.environ.get(
        "AGENTSWARM_OWNER_TOKEN"
    )
    if token:
        headers["X-Bootstrap-Token"] = token
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(f"{clean}/artifacts/{artifact_ref}", headers=headers)
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
