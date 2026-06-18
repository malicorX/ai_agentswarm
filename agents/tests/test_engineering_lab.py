from __future__ import annotations

import pytest

from agentswarm_agents.engineering_lab import (
    FIXTURES,
    apply_engineering_patch,
    default_verification_spec,
    list_fixtures,
    reset_fixture,
    run_fixture_tests,
)


@pytest.mark.parametrize("fixture", list_fixtures())
def test_fixture_patch_and_pytest_passes(fixture: str) -> None:
    reset_fixture(fixture)
    spec = FIXTURES[fixture]
    result = apply_engineering_patch(
        {
            "lab": {"fixture": fixture},
            "patch": {"file": spec.patch_file},
        }
    )
    assert result["applied"] is True
    tests = run_fixture_tests(default_verification_spec(fixture))
    assert tests["passed"] is True, tests.get("stdout") or tests.get("stderr")


def test_unknown_fixture_reset_raises() -> None:
    with pytest.raises(ValueError, match="unknown engineering fixture"):
        reset_fixture("not-a-fixture")
