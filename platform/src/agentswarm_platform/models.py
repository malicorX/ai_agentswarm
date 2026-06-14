from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    CREATED = "created"
    CLAIMED = "claimed"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentRegisterRequest(BaseModel):
    public_key: str
    owner: str
    capabilities: list[str]
    version_signature: str = "phase0-v1"


class AgentRegisterResponse(BaseModel):
    agent_id: str
    credential: str


class TaskCreateRequest(BaseModel):
    task_type: str
    capability_required: str
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_task_id: str | None = None
    parent_submission_id: str | None = None


class TaskEnvelope(BaseModel):
    task_id: str
    task_type: str
    capability_required: str
    status: TaskStatus
    payload: dict[str, Any]
    created_at: str
    parent_task_id: str | None = None


class ClaimRequest(BaseModel):
    agent_id: str


class ClaimResponse(BaseModel):
    claim_token: str
    deadline: str


class CheckpointRequest(BaseModel):
    claim_token: str
    partial_state: dict[str, Any] = Field(default_factory=dict)


class SubmitRequest(BaseModel):
    claim_token: str
    result: dict[str, Any]
    signature: str


class SubmitResponse(BaseModel):
    submission_id: str


class VerificationEnvelope(BaseModel):
    verification_id: str
    submission_id: str
    task_id: str
    task_type: str
    status: VerificationStatus
    result_summary: dict[str, Any]


class VerifyRequest(BaseModel):
    claim_token: str
    verdict: str
    notes: str = ""
    signature: str


class AuditEvent(BaseModel):
    seq: int
    timestamp: str
    event_type: str
    actor_id: str | None
    details: dict[str, Any]
    prev_hash: str
    entry_hash: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
