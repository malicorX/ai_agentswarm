"""Default capability sets for volunteer clients."""

from __future__ import annotations

# Roles a single home-machine volunteer can execute (engineering + creative pipelines).
GENERALIST_CAPABILITIES: tuple[str, ...] = (
    "coordinator",
    "codewriter",
    "tester",
    "sandbox.linux",
    "sandbox.build",
    "sandbox.test",
    "reviewer",
    "creative",
)


def default_generalist_capabilities() -> list[str]:
    return list(GENERALIST_CAPABILITIES)


def format_capabilities(capabilities: list[str]) -> str:
    return ",".join(capabilities)


def parse_capabilities_field(raw: str) -> list[str]:
    """Parse comma-separated capabilities; 'all' expands to the generalist set."""
    cleaned = raw.strip()
    if not cleaned or cleaned.lower() in ("all", "*", "any"):
        return default_generalist_capabilities()
    return [part.strip() for part in cleaned.split(",") if part.strip()]
