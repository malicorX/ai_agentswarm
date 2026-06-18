from __future__ import annotations

from agentswarm_agents.llama_io import parse_worker_container_failure


def test_parse_worker_container_failure_prefers_json_error() -> None:
    stderr = (
        "llama_new_context_with_model: n_ctx_per_seq (4096) < n_ctx_train (32768)\n"
        '{"error": "engineering fixture file not found: primes.py"}\n'
    )
    message = parse_worker_container_failure(stdout="", stderr=stderr, exit_code=1)
    assert message == "engineering fixture file not found: primes.py"


def test_parse_worker_container_failure_strips_llama_noise() -> None:
    stderr = "llama_load_model: some detail\nreal problem: disk full\n"
    message = parse_worker_container_failure(stdout="", stderr=stderr, exit_code=1)
    assert "real problem" in message
    assert "llama_load_model" not in message
