from __future__ import annotations

import pytest

from agentswarm_agents.engineering_lab import apply_engineering_patch, reset_fixture
from agentswarm_agents.sandbox_executor import (
    docker_available,
    ensure_sandbox_test_image,
    run_fixture_tests_sandbox,
)


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
def test_run_fixture_tests_sandbox_primes() -> None:
    reset_fixture("primes")
    apply_engineering_patch(
        {
            "lab": {"fixture": "primes", "lab": "engineering-lab"},
            "patch": {
                "file": "primes.py",
                "marker": "<!-- agentswarm:implement -->",
            },
        }
    )
    ensure_sandbox_test_image()
    result = run_fixture_tests_sandbox(
        {"fixture": "primes", "lab": "engineering-lab", "workspace_mode": "sandbox"}
    )
    assert result["sandbox"] is True
    assert result["passed"] is True
    assert result["fixture"] == "primes"
    assert result["sandbox_image"] == "agentswarm/sandbox-pytest:3.12.2"


def test_run_fixture_tests_sandbox_requires_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agentswarm_agents.sandbox_executor.docker_available",
        lambda: False,
    )
    with pytest.raises(RuntimeError, match="Docker is not available"):
        run_fixture_tests_sandbox({"fixture": "primes"})
