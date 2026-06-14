from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryUpsertRequest(BaseModel):
    key: str
    content: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    agent_id: str | None = None
    signature: str | None = None


class PlatformSummary(BaseModel):
    tasks: dict[str, int]
    replication_groups: dict[str, int]
    canary_failures_top: list[dict[str, Any]]
    memory_keys: list[str]
