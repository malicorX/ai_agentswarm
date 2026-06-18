from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPERS_SCRIPT = REPO_ROOT / "scripts" / "deploy_staging_helpers.py"


def _load_helpers():
    spec = importlib.util.spec_from_file_location("deploy_staging_helpers", HELPERS_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_request_deploy_skips_when_not_deployed(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_helpers()
    monkeypatch.setenv("AGENTSWARM_BOOTSTRAP_TOKEN", "boot")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/creative/goals/goal-1"):
            return httpx.Response(200, json={"status": "verified"})
        if request.method == "POST" and request.url.path.endswith("/artifacts"):
            return httpx.Response(
                200,
                json={
                    "artifact_ref": "sha256:" + "a" * 64,
                    "bytes": 24,
                    "sha256": "a" * 64,
                    "cached": False,
                },
            )
        if request.method == "POST" and request.url.path.endswith("/deploy-request"):
            return httpx.Response(404, json={"detail": "not found"})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://example.test/api") as client:
        body = mod.request_deploy_from_verified_goal(
            client, "https://example.test/api", "goal-1"
        )
    assert body["deploy_from_goal"] == "skipped_not_deployed"


def test_complete_deploy_signoff_chain_approves(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_helpers()
    state = {"status": "pending", "signoffs": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/agents/register"):
            return httpx.Response(200, json={"agent_id": f"agent-{state['signoffs']}"})
        if request.method == "POST" and request.url.path.endswith("/claim"):
            return httpx.Response(200, json={"claim_token": "tok"})
        if request.method == "POST" and request.url.path.endswith("/submit"):
            state["signoffs"] += 1
            if state["signoffs"] >= 1:
                state["status"] = "approved"
            return httpx.Response(200, json={"ok": True})
        if request.method == "GET" and "/deploy/requests/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "status": state["status"],
                    "execute_task_id": "task-exec",
                    "environment": "staging",
                    "artifact_ref": "sha256:" + "a" * 64,
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://example.test/api") as client:
        result = mod.complete_deploy_signoff_chain(
            client,
            "https://example.test/api",
            {
                "deploy_request_id": "deploy-1",
                "approve_task_ids": ["task-approve-1"],
            },
        )
    assert result["deploy_signoffs"] == "ok"
    assert result["deploy_status"] == "approved"
