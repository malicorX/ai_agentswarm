"""Shared helpers for live dispatch + volunteer integration tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_ASSIGNMENT_SECRET = "test-dispatch-secret-e2e"


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str, *, timeout_sec: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001 - probe until ready
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"platform did not become healthy at {base_url}: {last_error}")


def start_live_dispatch_platform(tmp_path: Path) -> tuple[str, subprocess.Popen[bytes]]:
    db_path = tmp_path / "platform.db"
    identity_dir = tmp_path / "identities"
    identity_dir.mkdir()
    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env.update(
        {
            "AGENTSWARM_DB": str(db_path),
            "AGENTSWARM_ARTIFACT_DIR": str(tmp_path / "artifacts"),
            "AGENTSWARM_AUTH_DISABLED": "1",
            "AGENTSWARM_ASSIGNMENT_MODE": "dispatch",
            "AGENTSWARM_ASSIGNMENT_SECRET": E2E_ASSIGNMENT_SECRET,
            "AGENTSWARM_IDENTITY_DIR": str(identity_dir),
        }
    )

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "agentswarm_platform.main:app",
        "--app-dir",
        str(REPO_ROOT / "platform" / "src"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_for_health(base_url)
    return base_url, proc


def stop_process(proc: subprocess.Popen[bytes]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
