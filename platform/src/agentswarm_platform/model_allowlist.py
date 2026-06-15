"""Platform-published volunteer LLM allowlist (ADR 0007)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib import resources
from typing import Any


def allowlist_enforced() -> bool:
    raw = os.environ.get("AGENTSWARM_MODEL_ALLOWLIST_ENFORCE", "").lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return False


@lru_cache(maxsize=1)
def load_model_allowlist() -> dict[str, Any]:
    override = os.environ.get("AGENTSWARM_MODEL_ALLOWLIST_JSON", "").strip()
    if override:
        data = json.loads(override)
        if not isinstance(data, dict):
            raise ValueError("AGENTSWARM_MODEL_ALLOWLIST_JSON must be a JSON object")
        return data
    raw = resources.files("agentswarm_platform").joinpath("data/model_allowlist.json").read_text(
        encoding="utf-8"
    )
    return json.loads(raw)


def list_allowed_models() -> list[dict[str, Any]]:
    return list(load_model_allowlist().get("models", []))


def allowed_model_ids() -> frozenset[str]:
    return frozenset(str(item["id"]) for item in list_allowed_models() if item.get("id"))


def get_model_entry(model_id: str) -> dict[str, Any] | None:
    for entry in list_allowed_models():
        if entry.get("id") == model_id:
            return entry
    return None


def validate_model_id(model_id: str | None) -> None:
    if not model_id or not allowlist_enforced():
        return
    if model_id not in allowed_model_ids():
        known = ", ".join(sorted(allowed_model_ids()))
        raise ValueError(f"model_id {model_id!r} is not on the platform allowlist ({known})")


def public_parameters() -> dict[str, Any]:
    data = load_model_allowlist()
    return {
        "version": str(data.get("version", "1")),
        "enforced": allowlist_enforced(),
        "allowlist": list_allowed_models(),
    }
