from __future__ import annotations

import base64
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

import httpx

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.dispatch_client import CapsuleExecutor, DispatchClient
from agentswarm_agents.docker_worker import (
    docker_available,
    docker_capsule_executor,
    verify_assignment_signature,
)
from agentswarm_agents.ollama_executor import ollama_available, ollama_capsule_executor
from agentswarm_agents.identity import StoredIdentity, load_identity, save_identity
from agentswarm_agents.model_allowlist import validate_model_id
from agentswarm_agents.owner_auth import owner_auth_headers
from agentswarm_platform.crypto import generate_keypair, public_key_b64

CLIENT_VERSION = "0.6.0-p6.8"
LogCallback = Callable[[str], None]
StateCallback = Callable[[str, str], None]


class VolunteerState(str, Enum):
    CONNECTING = "connecting"
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


@dataclass(frozen=True)
class VolunteerConfig:
    agent_name: str
    base_url: str
    owner: str
    capabilities: list[str]
    model_id: str
    worker_image: str = "agentswarm-worker:dev"
    poll_sec: float = 2.0
    wait_timeout_sec: float = 30.0
    heartbeat_ttl_sec: int = 120
    vram_gb: float | None = None


def resolve_reported_vram_gb(config: VolunteerConfig) -> float | None:
    if config.vram_gb is not None:
        return config.vram_gb
    raw = os.environ.get("AGENTSWARM_VRAM_GB", "").strip()
    if raw:
        return float(raw)
    if "reviewer" in config.capabilities:
        return 8.0
    return None


def connect_dispatch_agent(config: VolunteerConfig) -> DispatchClient:
    url = config.base_url.rstrip("/")
    stored = load_identity(config.agent_name)
    if stored is not None:
        priv = base64.urlsafe_b64decode(stored.private_key_b64.encode("ascii"))
        pub_b64 = stored.public_key_b64
    else:
        pub, priv = generate_keypair()
        pub_b64 = public_key_b64(pub)

    response = httpx.post(
        f"{url}/agents/register",
        json={
            "public_key": pub_b64,
            "owner": config.owner,
            "capabilities": config.capabilities,
        },
        headers=owner_auth_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    agent_id = response.json()["agent_id"]
    save_identity(
        StoredIdentity(
            agent_name=config.agent_name,
            agent_id=agent_id,
            public_key_b64=pub_b64,
            private_key_b64=base64.urlsafe_b64encode(priv).decode("ascii"),
            owner=config.owner,
            capabilities=config.capabilities,
        )
    )
    return DispatchClient(url, agent_id, priv)


def resolve_executor(config: VolunteerConfig, agent_id: str) -> CapsuleExecutor:
    model = validate_model_id(config.model_id)
    runtime = str(model.get("runtime", "in-process"))
    if runtime == "docker":
        if not docker_available():
            raise RuntimeError(
                "selected model requires Docker Desktop; build the worker image first"
            )
        return docker_capsule_executor(agent_id, image=config.worker_image)
    if runtime == "ollama":
        endpoint = str(model.get("endpoint", "http://127.0.0.1:11434"))
        if not ollama_available(endpoint):
            raise RuntimeError(
                f"selected model requires a local Ollama server at {endpoint}; "
                "start Ollama and pull the model, or use llm-mock-v1"
            )
        return ollama_capsule_executor(agent_id, model_entry=model)
    return execute_capsule


def assert_platform_model_allowlist(base_url: str, model_id: str) -> None:
    """Ensure the client model_id is published on the platform allowlist."""
    response = httpx.get(f"{base_url.rstrip('/')}/platform/config", timeout=15.0)
    response.raise_for_status()
    models = response.json().get("models")
    if not isinstance(models, dict):
        return
    allowlist = models.get("allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        return
    allowed = {str(item["id"]) for item in allowlist if isinstance(item, dict) and item.get("id")}
    if model_id not in allowed:
        known = ", ".join(sorted(allowed))
        raise RuntimeError(
            f"model_id {model_id!r} is not on the platform allowlist ({known})"
        )


def assert_dispatch_mode(base_url: str) -> None:
    response = httpx.get(f"{base_url.rstrip('/')}/platform/config", timeout=15.0)
    response.raise_for_status()
    mode = response.json().get("assignment_mode", "pull")
    if mode != "dispatch":
        raise RuntimeError(
            f"platform assignment_mode is {mode!r}; volunteer client requires dispatch"
        )


class VolunteerClient:
    def __init__(
        self,
        config: VolunteerConfig,
        *,
        on_state: StateCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> None:
        self.config = config
        self._on_state = on_state
        self._on_log = on_log
        self._client: DispatchClient | None = None
        self._executor: CapsuleExecutor | None = None

    @property
    def agent_id(self) -> str | None:
        if self._client is None:
            return None
        return self._client.agent_id

    def _log(self, message: str) -> None:
        if self._on_log is not None:
            self._on_log(message)

    def _set_state(self, state: VolunteerState | str, detail: str = "") -> None:
        if self._on_state is not None:
            self._on_state(str(state), detail)

    def connect(self) -> DispatchClient:
        self._set_state(VolunteerState.CONNECTING, "checking platform mode")
        assert_dispatch_mode(self.config.base_url)
        validate_model_id(self.config.model_id)
        assert_platform_model_allowlist(self.config.base_url, self.config.model_id)
        self._set_state(VolunteerState.CONNECTING, "registering agent")
        client = connect_dispatch_agent(self.config)
        self._executor = resolve_executor(self.config, client.agent_id)
        self._client = client
        self._log(f"connected as {client.agent_id}")
        return client

    def run_once(self) -> bool:
        if self._client is None or self._executor is None:
            raise RuntimeError("call connect() before run_once()")
        client = self._client
        config = self.config
        reported_vram = resolve_reported_vram_gb(config)
        client.heartbeat(
            config.capabilities,
            status="idle",
            model_id=config.model_id,
            client_version=CLIENT_VERSION,
            ttl_sec=config.heartbeat_ttl_sec,
            vram_gb=reported_vram,
        )
        assignment = client.wait_for_assignment(
            poll_sec=config.poll_sec,
            timeout_sec=config.wait_timeout_sec,
        )
        if assignment is None:
            return False
        verify_assignment_signature(assignment, client.agent_id)
        task_type = assignment.get("task_type", "assignment")
        self._set_state(VolunteerState.RUNNING, task_type)
        self._log(f"running {task_type} ({assignment.get('task_id')})")
        result = self._executor(assignment)
        submission_id = client.submit_assignment(assignment, result)
        client.heartbeat(
            config.capabilities,
            status="idle",
            model_id=config.model_id,
            client_version=CLIENT_VERSION,
            ttl_sec=config.heartbeat_ttl_sec,
            vram_gb=reported_vram,
        )
        self._set_state(VolunteerState.IDLE, "waiting for assignment")
        self._log(f"submitted {submission_id}")
        return True

    def run_until_stopped(self, stop_event: threading.Event) -> None:
        try:
            self.connect()
            self._set_state(VolunteerState.IDLE, "waiting for assignment")
            while not stop_event.is_set():
                try:
                    worked = self.run_once()
                except Exception as exc:
                    self._set_state(VolunteerState.ERROR, str(exc))
                    self._log(f"error: {exc}")
                    stop_event.wait(self.config.poll_sec)
                    if stop_event.is_set():
                        break
                    self._set_state(VolunteerState.IDLE, "retrying")
                    continue
                if not worked:
                    stop_event.wait(self.config.poll_sec)
        except Exception as exc:
            self._set_state(VolunteerState.ERROR, str(exc))
            self._log(f"fatal: {exc}")


def run_headless(config: VolunteerConfig, *, loops: int = 0) -> int:
    stop = threading.Event()
    volunteer = VolunteerClient(config, on_log=print)
    volunteer.connect()
    completed = 0
    while not stop.is_set():
        if volunteer.run_once():
            completed += 1
            if loops and completed >= loops:
                break
        else:
            time.sleep(config.poll_sec)
    return completed
