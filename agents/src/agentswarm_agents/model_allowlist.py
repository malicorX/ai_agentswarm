from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib import resources
from typing import Any


def allowlist_enforced() -> bool:
    return os.environ.get("AGENTSWARM_ALLOWLIST_SKIP", "").lower() not in (
        "1",
        "true",
        "yes",
    )


@lru_cache(maxsize=1)
def load_model_allowlist() -> dict[str, Any]:
    raw = resources.files("agentswarm_agents").joinpath("model_allowlist.json").read_text(
        encoding="utf-8"
    )
    return json.loads(raw)


def list_allowed_models() -> list[dict[str, Any]]:
    data = load_model_allowlist()
    return list(data.get("models", []))


def get_model_entry(model_id: str) -> dict[str, Any] | None:
    for entry in list_allowed_models():
        if entry.get("id") == model_id:
            return entry
    return None


def validate_model_id(model_id: str) -> dict[str, Any]:
    if not allowlist_enforced():
        return {"id": model_id, "label": model_id, "runtime": "in-process"}
    entry = get_model_entry(model_id)
    if entry is None:
        known = ", ".join(str(item["id"]) for item in list_allowed_models())
        raise ValueError(f"model_id {model_id!r} is not on the client allowlist ({known})")
    return entry


def default_model_id() -> str:
    models = list_allowed_models()
    if not models:
        return "llm-mock-v1"
    return str(models[0]["id"])
