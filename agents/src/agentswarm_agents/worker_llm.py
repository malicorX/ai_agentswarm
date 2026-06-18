"""GGUF inference inside the Docker worker container."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from agentswarm_agents.coordinator_planner import (
    build_deterministic_coordinator_plan,
    coordinator_llm_enabled,
    goal_from_capsule,
)
from agentswarm_agents.engineering_lab import IMPLEMENT_MARKER, get_fixture_spec
from agentswarm_agents.ollama_executor import (
    _creative_text_prompt,
    _normalize_reviewer_result,
    _parse_json_object,
    _reviewer_subjective_prompt,
)

from agentswarm_agents.llama_io import (
    install_llama_log_sink,
    suppress_native_stderr,
)


def model_path_from_env() -> str | None:
    raw = os.environ.get("AGENTSWARM_MODEL_PATH", "").strip()
    return raw or None


def engineering_llm_enabled() -> bool:
    raw = os.environ.get("AGENTSWARM_ENGINEERING_LLM", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def _load_llama():
    from llama_cpp import Llama

    path = model_path_from_env()
    if not path:
        raise RuntimeError("AGENTSWARM_MODEL_PATH is not set")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"model weights not found: {path}")
    n_gpu = int(os.environ.get("AGENTSWARM_LLAMA_N_GPU_LAYERS", "-1"))
    n_ctx = int(os.environ.get("AGENTSWARM_LLAMA_N_CTX", "4096"))
    with suppress_native_stderr():
        install_llama_log_sink()
        return Llama(model_path=path, n_gpu_layers=n_gpu, n_ctx=n_ctx, verbose=False)


def llama_chat(messages: list[dict[str, str]], *, timeout_sec: float = 120.0) -> str:
    del timeout_sec  # llama-cpp-python does not expose per-call HTTP timeouts
    with suppress_native_stderr():
        llama = _load_llama()
        response = llama.create_chat_completion(messages=messages, temperature=0.2)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("llama response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("llama response missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("llama response missing message content")
    return content.strip()


def _coordinator_decompose_prompt(capsule: dict[str, Any]) -> list[dict[str, str]]:
    goal = goal_from_capsule(capsule)
    example = build_deterministic_coordinator_plan(capsule)
    return [
        {
            "role": "system",
            "content": (
                "You are a coordinator for AgentSwarm subjective goals. "
                "Respond with JSON only: "
                '{"goal_id": "...", "pool_needs": [...], "deferred_pool_needs": [...]}. '
                "Use only task_type creative.text in pool_needs and reviewer.subjective "
                "in deferred_pool_needs."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Goal:\n{json.dumps(goal)}\n\n"
                f"Valid example plan:\n{json.dumps(example)}"
            ),
        },
    ]


def _engineering_patch_prompt(capsule: dict[str, Any]) -> list[dict[str, str]]:
    lab = capsule.get("lab") or {}
    patch = capsule.get("patch") or {}
    fixture = str(lab.get("fixture", "primes"))
    spec = get_fixture_spec(fixture)
    rel_file = str(patch.get("file", spec.patch_file))
    brief = str(capsule.get("brief") or capsule.get("goal_brief") or "Implement the engineering task.")
    return [
        {
            "role": "system",
            "content": (
                "You are an engineering codewriter for AgentSwarm. "
                "Respond with Python source only — no markdown fences, no commentary. "
                f"The code will be inserted after the marker {IMPLEMENT_MARKER!r} in the target file."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Brief:\n{brief}\n\n"
                f"Fixture: {fixture}\n"
                f"Target file: {rel_file}\n\n"
                f"Current stub:\n{spec.stub}\n\n"
                "Write the implementation body."
            ),
        },
    ]


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    fence_match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", stripped)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def execute_capsule_with_local_llm(assignment: dict[str, Any]) -> dict[str, Any]:
    from agentswarm_agents.capsule_executor import execute_capsule
    from agentswarm_agents.engineering_lab import apply_engineering_patch

    if model_path_from_env() is None:
        return execute_capsule(assignment)

    task_type = str(assignment.get("task_type", ""))
    capsule = assignment.get("capsule") or {}
    if not isinstance(capsule, dict):
        capsule = {}

    if task_type == "coordinator.decompose" and coordinator_llm_enabled():
        try:
            from agentswarm_platform.coordinator_plan import validate_coordinator_plan

            content = llama_chat(_coordinator_decompose_prompt(capsule))
            parsed = _parse_json_object(content)
            goal_id = str(capsule.get("goal_id", ""))
            return validate_coordinator_plan(parsed, goal_id=goal_id)
        except (ValueError, RuntimeError, json.JSONDecodeError):
            return build_deterministic_coordinator_plan(capsule)

    if task_type == "engineering.infer_patch" and engineering_llm_enabled():
        if isinstance(capsule.get("lab"), dict) and isinstance(capsule.get("patch"), dict):
            content = llama_chat(_engineering_patch_prompt(capsule))
            return {"insert": _strip_code_fences(content)}

    if task_type == "codewriter.patch" and engineering_llm_enabled():
        if isinstance(capsule.get("git"), dict):
            return execute_capsule(assignment)
        if isinstance(capsule.get("lab"), dict) and isinstance(capsule.get("patch"), dict):
            try:
                content = llama_chat(_engineering_patch_prompt(capsule))
                insert = _strip_code_fences(content)
                enriched = dict(capsule)
                enriched["patch"] = {**capsule["patch"], "insert": insert}
                return apply_engineering_patch(enriched)
            except (ValueError, RuntimeError, json.JSONDecodeError, OSError):
                return execute_capsule(assignment)

    if task_type not in _LLM_TASK_TYPES:
        return execute_capsule(assignment)

    if task_type == "creative.text":
        content = llama_chat(_creative_text_prompt(capsule))
        return {"text": content}

    if task_type == "reviewer.subjective":
        content = llama_chat(_reviewer_subjective_prompt(capsule))
        parsed = _parse_json_object(content)
        return _normalize_reviewer_result(parsed, capsule)

    return execute_capsule(assignment)
