from __future__ import annotations

import pytest

from agentswarm_platform.forge_types import (
    ALLOWED_FORGE_TYPES,
    validate_forge_type,
)


@pytest.mark.parametrize("forge_type", sorted(ALLOWED_FORGE_TYPES))
def test_validate_forge_type_accepts_known_labels(forge_type: str) -> None:
    assert validate_forge_type(forge_type) == forge_type
    assert validate_forge_type(forge_type.upper()) == forge_type


def test_validate_forge_type_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="forge_type"):
        validate_forge_type("bitbucket")
