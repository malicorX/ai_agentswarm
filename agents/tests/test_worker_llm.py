from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentswarm_agents.worker_llm import (
    _strip_code_fences,
    execute_capsule_with_local_llm,
)


def test_strip_code_fences() -> None:
    assert _strip_code_fences("```python\nprint(1)\n```") == "print(1)"


def test_execute_capsule_without_model_path_uses_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTSWARM_MODEL_PATH", raising=False)
    result = execute_capsule_with_local_llm(
        {"task_type": "creative.text", "capsule": {"brief": "winter"}},
    )
    assert "winter" in result["text"]
    assert "Container poem" in result["text"]


def test_execute_capsule_with_mock_llama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSWARM_MODEL_PATH", "/models/weights/model.gguf")

    class _FakeLlama:
        def __init__(self, **kwargs):
            del kwargs

        def create_chat_completion(self, **kwargs):
            del kwargs
            return {"choices": [{"message": {"content": "Generated poem about winter."}}]}

    monkeypatch.setattr("agentswarm_agents.worker_llm._load_llama", lambda: _FakeLlama())
    monkeypatch.setattr("agentswarm_agents.worker_llm.os.path.isfile", lambda path: True)

    result = execute_capsule_with_local_llm(
        {"task_type": "creative.text", "capsule": {"brief": "winter"}},
    )
    assert result == {"text": "Generated poem about winter."}


def test_engineering_llm_codewriter(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTSWARM_MODEL_PATH", "/models/weights/model.gguf")
    monkeypatch.setenv("AGENTSWARM_ENGINEERING_LLM", "1")
    monkeypatch.setenv("AGENTSWARM_REPO_ROOT", str(tmp_path))

    from agentswarm_agents.engineering_lab import reset_fixture

    reset_fixture("primes")

    code = "def main():\n    print('ok')\n"

    class _FakeLlama:
        def create_chat_completion(self, **kwargs):
            del kwargs
            return {"choices": [{"message": {"content": code}}]}

    monkeypatch.setattr("agentswarm_agents.worker_llm._load_llama", lambda: _FakeLlama())
    monkeypatch.setattr("agentswarm_agents.worker_llm.os.path.isfile", lambda path: True)

    result = execute_capsule_with_local_llm(
        {
            "task_type": "codewriter.patch",
            "capsule": {
                "lab": {"fixture": "primes", "lab": "engineering-lab"},
                "patch": {"file": "primes.py"},
                "brief": "write primes",
            },
        }
    )
    assert result["applied"] is True
    assert "main" in (tmp_path / "pilot" / "engineering-lab" / "primes" / "primes.py").read_text()
