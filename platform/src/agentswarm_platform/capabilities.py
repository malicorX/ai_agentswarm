from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PACKAGE_REGISTRY = Path(__file__).resolve().parent / "data" / "capabilities.json"
_REPO_REGISTRY = (
    Path(__file__).resolve().parents[3] / "docs" / "protocol" / "capabilities.json"
)

_FALLBACK_CAPABILITIES = frozenset(
    {
        "codewriter",
        "tester",
        "sandbox.linux",
        "sandbox.build",
        "sandbox.test",
        "sandbox.windows",
        "sandbox.windows.build",
        "sandbox.windows.test",
        "reviewer",
        "summarizer",
        "scraper",
        "researcher",
        "deployer",
        "planner",
        "orchestrator",
        "classifier",
        "moderator",
        "creative",
        "coordinator",
    }
)


def _registry_path() -> Path | None:
    if _REPO_REGISTRY.is_file():
        return _REPO_REGISTRY
    if _PACKAGE_REGISTRY.is_file():
        return _PACKAGE_REGISTRY
    return None


def load_capability_registry() -> dict[str, Any]:
    path = _registry_path()
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "version": "1",
        "capabilities": [{"id": c, "task_types": []} for c in sorted(_FALLBACK_CAPABILITIES)],
    }


def known_capability_ids() -> frozenset[str]:
    data = load_capability_registry()
    return frozenset(item["id"] for item in data.get("capabilities", []))


def agent_satisfies_capability(agent_capabilities: list[str], required: str) -> bool:
    """Whether an agent's advertised capabilities can claim a task need."""
    if required in agent_capabilities:
        return True
    # Legacy single-worker hosts may still advertise only sandbox.linux.
    if required in ("sandbox.build", "sandbox.test") and "sandbox.linux" in agent_capabilities:
        return True
    if required in ("sandbox.windows.build", "sandbox.windows.test") and (
        "sandbox.windows" in agent_capabilities
    ):
        return True
    return False


def validate_capabilities(capabilities: list[str]) -> None:
    if not capabilities:
        raise ValueError("at least one capability is required")
    known = known_capability_ids()
    unknown = [c for c in capabilities if c not in known]
    if unknown:
        raise ValueError(f"unknown capabilities: {', '.join(unknown)}")


def validate_version_signature(version_signature: str) -> None:
    from agentswarm_platform.agent_versioning import validate_version_signature as _validate

    _validate(version_signature)


def capabilities_requiring_explicit_egress() -> frozenset[str]:
    data = load_capability_registry()
    required: set[str] = set()
    for item in data.get("capabilities", []):
        if item.get("requires_explicit_egress"):
            required.add(str(item["id"]))
    return frozenset(required)
