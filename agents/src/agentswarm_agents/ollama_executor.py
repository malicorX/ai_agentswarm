from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.docker_worker import verify_assignment_signature

_LLM_TASK_TYPES = frozenset({"creative.text", "reviewer.subjective"})


def validate_ollama_endpoint(endpoint: str) -> str:
    """Ensure the Ollama base URL is localhost-only (ADR 0007)."""
    clean = endpoint.strip().rstrip("/")
    if not clean:
        raise ValueError("ollama endpoint is required")
    parsed = urlparse(clean)
    if parsed.scheme != "http":
        raise ValueError("ollama endpoint must use http://")
    host = (parsed.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("ollama endpoint must be http://127.0.0.1 or http://localhost")
    if parsed.username or parsed.password:
        raise ValueError("ollama endpoint must not include credentials")
    return clean


def ollama_model_name(model_entry: dict[str, Any]) -> str:
    explicit = model_entry.get("ollama_model")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    model_id = str(model_entry.get("id", ""))
    if "/" in model_id:
        return model_id.split("/", 1)[1]
    return model_id


def ollama_available(endpoint: str, *, timeout_sec: float = 5.0) -> bool:
    base = validate_ollama_endpoint(endpoint)
    try:
        response = httpx.get(f"{base}/api/tags", timeout=timeout_sec)
    except (httpx.HTTPError, OSError):
        return False
    return response.status_code == 200


def ollama_chat(
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    timeout_sec: float = 120.0,
) -> str:
    base = validate_ollama_endpoint(endpoint)
    response = httpx.post(
        f"{base}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=timeout_sec,
    )
    response.raise_for_status()
    body = response.json()
    message = body.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("ollama response missing message object")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("ollama response missing message content")
    return content.strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object")
    return parsed


def _creative_text_prompt(capsule: dict[str, Any]) -> list[dict[str, str]]:
    brief = str(capsule.get("brief", "creative work"))
    return [
        {
            "role": "system",
            "content": (
                "You are a creative writer for AgentSwarm. "
                "Respond with only the requested creative text — no titles, labels, or markdown fences."
            ),
        },
        {"role": "user", "content": f"Brief:\n{brief}\n\nWrite the creative text."},
    ]


def _reviewer_subjective_prompt(capsule: dict[str, Any]) -> list[dict[str, str]]:
    rubric = capsule.get("rubric") or [{"id": "quality", "weight": 1.0}]
    rubric_lines = []
    score_keys: list[str] = []
    for item in rubric:
        if not isinstance(item, dict):
            continue
        rubric_id = str(item.get("id", "quality"))
        score_keys.append(rubric_id)
        weight = item.get("weight", 1.0)
        rubric_lines.append(f"- {rubric_id} (weight {weight})")
    rubric_text = "\n".join(rubric_lines) or "- quality (weight 1.0)"
    score_keys = score_keys or ["quality"]
    example_scores = ", ".join(f'"{key}": 8.0' for key in score_keys)
    artifact = capsule.get("artifact_text")
    artifact_block = f"\n\nSubmission:\n{artifact}" if artifact else ""
    return [
        {
            "role": "system",
            "content": (
                "You are a subjective reviewer for AgentSwarm. "
                f'Respond with JSON only: {{"scores": {{{example_scores}}}, "rationale": "..."}}. '
                "Use numeric scores from 0 to 10 for each rubric id."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Brief:\n{capsule.get('brief', '')}\n\nRubric:\n{rubric_text}{artifact_block}"
            ),
        },
    ]


def _normalize_reviewer_result(raw: dict[str, Any], capsule: dict[str, Any]) -> dict[str, Any]:
    rubric = capsule.get("rubric") or [{"id": "quality", "weight": 1.0}]
    scores_in = raw.get("scores")
    if not isinstance(scores_in, dict):
        raise ValueError("reviewer result requires scores object")
    scores: dict[str, float] = {}
    for item in rubric:
        if not isinstance(item, dict):
            continue
        rubric_id = str(item.get("id", "quality"))
        value = scores_in.get(rubric_id, 7.0)
        scores[rubric_id] = float(value)
    if not scores:
        scores["quality"] = float(scores_in.get("quality", 7.0))
    rationale = raw.get("rationale", "")
    if not isinstance(rationale, str):
        raise ValueError("reviewer rationale must be a string")
    return {"scores": scores, "rationale": rationale.strip() or "Ollama reviewer response."}


def execute_capsule_with_ollama(
    assignment: dict[str, Any],
    *,
    model_entry: dict[str, Any],
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    task_type = str(assignment.get("task_type", ""))
    capsule = assignment.get("capsule") or {}
    if not isinstance(capsule, dict):
        capsule = {}

    if task_type not in _LLM_TASK_TYPES:
        return execute_capsule(assignment)

    endpoint = str(model_entry.get("endpoint", "http://127.0.0.1:11434"))
    model = ollama_model_name(model_entry)
    if task_type == "creative.text":
        content = ollama_chat(
            endpoint,
            model,
            _creative_text_prompt(capsule),
            timeout_sec=timeout_sec,
        )
        return {"text": content}

    if task_type == "reviewer.subjective":
        content = ollama_chat(
            endpoint,
            model,
            _reviewer_subjective_prompt(capsule),
            timeout_sec=timeout_sec,
        )
        parsed = _parse_json_object(content)
        return _normalize_reviewer_result(parsed, capsule)

    return execute_capsule(assignment)


def ollama_capsule_executor(
    agent_id: str,
    *,
    model_entry: dict[str, Any],
    timeout_sec: float = 120.0,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _executor(assignment: dict[str, Any]) -> dict[str, Any]:
        verify_assignment_signature(assignment, agent_id)
        return execute_capsule_with_ollama(
            assignment,
            model_entry=model_entry,
            timeout_sec=timeout_sec,
        )

    return _executor
