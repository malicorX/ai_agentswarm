"""Forge type labels for git-backed capsules (ADR 0009)."""

from __future__ import annotations

ALLOWED_FORGE_TYPES = frozenset({"git", "github", "gitlab"})
DEFAULT_FORGE_TYPE = "git"


def validate_forge_type(forge_type: str) -> str:
    """Return normalized forge_type or raise ValueError."""
    normalized = forge_type.strip().lower()
    if normalized not in ALLOWED_FORGE_TYPES:
        known = ", ".join(sorted(ALLOWED_FORGE_TYPES))
        raise ValueError(f"forge_type must be one of {known}")
    return normalized


def forge_execution_is_git_cli() -> bool:
    """v1 always executes via local git; forge_type does not change the runtime."""
    return True
