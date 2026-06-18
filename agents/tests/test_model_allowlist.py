from __future__ import annotations

import pytest

from agentswarm_agents.model_allowlist import (
    get_model_entry,
    list_allowed_models,
    validate_model_id,
)


def test_allowlist_contains_mock_model() -> None:
    models = list_allowed_models()
    assert any(item["id"] == "llm-mock-v1" for item in models)


def test_validate_model_id_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_ALLOWLIST_SKIP", raising=False)
    with pytest.raises(ValueError, match="allowlist"):
        validate_model_id("not-a-real-model")


def test_validate_model_id_allows_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_ALLOWLIST_SKIP", "1")
    entry = validate_model_id("custom-model")
    assert entry["id"] == "custom-model"


def test_get_model_entry_docker_runtime() -> None:
    entry = get_model_entry("llm-docker-worker-v1")
    assert entry is not None
    assert entry["runtime"] == "docker"
    assert entry.get("worker_image")


def test_get_model_entry_docker_weighted_model() -> None:
    entry = get_model_entry("docker/qwen2.5-coder-3b")
    assert entry is not None
    assert entry["runtime"] == "docker"
    assert entry["weight"]["format"] == "gguf"


def test_allowlist_documents_ollama_localhost() -> None:
    entry = get_model_entry("ollama/llama3.2")
    assert entry is not None
    assert entry["runtime"] == "ollama"
    assert entry.get("local_only") is True
    assert str(entry.get("endpoint", "")).startswith("http://127.0.0.1")
