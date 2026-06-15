from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

from agentswarm_agents.client import platform_url
from agentswarm_agents.workers.orchestrator import ensure_scan_task


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    module: str


DEFAULT_WORKERS: tuple[WorkerSpec, ...] = (
    WorkerSpec("planner", "agentswarm_agents.workers.planner"),
    WorkerSpec("orchestrator", "agentswarm_agents.workers.orchestrator"),
    WorkerSpec("moderator", "agentswarm_agents.workers.moderator"),
    WorkerSpec("deployer", "agentswarm_agents.workers.deployer"),
    WorkerSpec("codewriter", "agentswarm_agents.workers.codewriter"),
    WorkerSpec("tester", "agentswarm_agents.workers.tester"),
    WorkerSpec("reviewer", "agentswarm_agents.workers.reviewer"),
)


def _worker_command(spec: WorkerSpec, poll_interval: float) -> list[str]:
    return [
        sys.executable,
        "-m",
        spec.module,
        "--poll-interval",
        str(poll_interval),
    ]


def _scan_loop(
    base_url: str,
    project_id: str,
    interval_sec: float,
    stop: threading.Event,
) -> None:
    while not stop.wait(interval_sec):
        try:
            ensure_scan_task(base_url, project_id=project_id)
        except Exception as exc:  # noqa: BLE001 — keep supervisor alive
            print(f"swarm: orchestrator enqueue-scan failed: {exc}", flush=True)


def run_supervisor(
    *,
    workers: tuple[WorkerSpec, ...] = DEFAULT_WORKERS,
    poll_interval: float = 2.0,
    scan_interval_sec: float | None = None,
    project_id: str = "default",
    spawn: Callable[[list[str]], subprocess.Popen] = subprocess.Popen,
) -> int:
    base_url = platform_url()
    scan_interval = scan_interval_sec
    if scan_interval is None:
        raw = os.environ.get("AGENTSWARM_ORCHESTRATOR_SCAN_INTERVAL_SEC", "900").strip()
        scan_interval = float(raw) if raw else 900.0

    stop = threading.Event()
    shutting_down = False
    spec_by_name = {spec.name: spec for spec in workers}

    if scan_interval > 0:
        scan_thread = threading.Thread(
            target=_scan_loop,
            args=(base_url, project_id, scan_interval, stop),
            name="orchestrator-scan",
            daemon=True,
        )
        scan_thread.start()
        ensure_scan_task(base_url, project_id=project_id)

    processes: list[tuple[str, subprocess.Popen]] = []
    for spec in workers:
        proc = spawn(_worker_command(spec, poll_interval))
        processes.append((spec.name, proc))
        print(f"swarm: started {spec.name} (pid {proc.pid})", flush=True)

    def shutdown(*_args: object) -> None:
        nonlocal shutting_down
        shutting_down = True
        stop.set()
        for name, proc in processes:
            if proc.poll() is None:
                print(f"swarm: stopping {name} (pid {proc.pid})", flush=True)
                proc.terminate()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        while not shutting_down:
            for index, (name, proc) in enumerate(processes):
                code = proc.poll()
                if code is not None:
                    print(
                        f"swarm: worker {name} exited with {code}, restarting",
                        flush=True,
                    )
                    spec = spec_by_name[name]
                    processes[index] = (
                        name,
                        spawn(_worker_command(spec, poll_interval)),
                    )
            time.sleep(1.0)
    finally:
        stop.set()
        deadline = time.time() + 10.0
        for _name, proc in processes:
            if proc.poll() is None:
                proc.wait(timeout=max(0, deadline - time.time()))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentSwarm production worker supervisor")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument(
        "--scan-interval",
        type=float,
        default=None,
        help="Seconds between orchestrator.scan enqueues (0 disables)",
    )
    parser.add_argument("--project-id", default="default")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print worker commands and exit",
    )
    args = parser.parse_args()

    if args.dry_run:
        for spec in DEFAULT_WORKERS:
            print(" ".join(_worker_command(spec, args.poll_interval)))
        return 0

    return run_supervisor(
        poll_interval=args.poll_interval,
        scan_interval_sec=args.scan_interval,
        project_id=args.project_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
