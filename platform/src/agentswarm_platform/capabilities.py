from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "protocol" / "capabilities.json"
)

_FALLBACK_CAPABILITIES = frozenset(
    {
        "codewriter",
        "tester",
        "reviewer",
        "summarizer",
        "scraper",
        "researcher",
        "deployer",
        "planner",
        "orchestrator",
        "moderator",
    }
)


def load_capability_registry() -> dict[str, Any]:
    if _REGISTRY_PATH.exists():
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {
        "version": "1",
        "capabilities": [{"id": c, "task_types": []} for c in sorted(_FALLBACK_CAPABILITIES)],
    }


def known_capability_ids() -> frozenset[str]:
    data = load_capability_registry()
    return frozenset(item["id"] for item in data.get("capabilities", []))


def validate_capabilities(capabilities: list[str]) -> None:
    if not capabilities:
        raise ValueError("at least one capability is required")
    known = known_capability_ids()
    unknown = [c for c in capabilities if c not in known]
    if unknown:
        raise ValueError(f"unknown capabilities: {', '.join(unknown)}")


def validate_version_signature(version_signature: str) -> None:
    if len(version_signature.strip()) < 8:
        raise ValueError("version_signature must be at least 8 characters")


def capabilities_requiring_explicit_egress() -> frozenset[str]:
    data = load_capability_registry()
    required: set[str] = set()
    for item in data.get("capabilities", []):
        if item.get("requires_explicit_egress"):
            required.add(str(item["id"]))
    return frozenset(required)
