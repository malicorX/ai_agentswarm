from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def load_governance_templates() -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    root = resources.files("agentswarm_platform").joinpath("templates/governance")
    for path in root.iterdir():
        if path.suffix != ".json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        template_id = raw.get("template_id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError(f"invalid governance template file: {path.name}")
        defaults = raw.get("defaults")
        if defaults is not None and not isinstance(defaults, dict):
            raise ValueError(f"governance template defaults must be an object: {template_id}")
        templates[template_id] = {
            "template_id": template_id,
            "name": str(raw.get("name", template_id)),
            "description": raw.get("description"),
            "defaults": defaults or {},
        }
    return templates


def list_governance_templates() -> list[dict[str, Any]]:
    return [
        {
            "template_id": template["template_id"],
            "name": template["name"],
            "description": template["description"],
        }
        for template in sorted(
            load_governance_templates().values(),
            key=lambda item: item["template_id"],
        )
    ]


def get_governance_template(template_id: str) -> dict[str, Any] | None:
    return load_governance_templates().get(template_id.strip())


def resolve_governance_config(template_id: str | None) -> tuple[str | None, dict[str, Any]]:
    if not template_id:
        return None, {}
    template = get_governance_template(template_id)
    if template is None:
        raise ValueError(f"unknown governance template: {template_id}")
    return template_id, dict(template["defaults"])
