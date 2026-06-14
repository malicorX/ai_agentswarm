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
    resource_budget: dict[str, int] | None = None
    egress_allowlist: list[str] | None = None
    project_ids: list[str] | None = None


class AgentBudgetUsage(BaseModel):
    concurrent_claims: int
    claims_last_hour: int


class AgentBudgetStatus(BaseModel):
    agent_id: str
    resource_budget: dict[str, int]
    egress_allowlist: list[str]
    usage: AgentBudgetUsage


class AgentRegisterResponse(BaseModel):
    agent_id: str
    credential: str


class TaskCreateRequest(BaseModel):
    task_type: str
    capability_required: str
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_task_id: str | None = None
    parent_submission_id: str | None = None
    project_id: str | None = None


class ProjectCreateRequest(BaseModel):
    project_id: str | None = None
    name: str
    description: str | None = None


class ProjectEnvelope(BaseModel):
    project_id: str
    name: str
    description: str | None = None
    created_at: str


class TaskEnvelope(BaseModel):
    task_id: str
    task_type: str
    capability_required: str
    status: TaskStatus
    payload: dict[str, Any]
    created_at: str
    parent_task_id: str | None = None
    project_id: str = "default"


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
    replication_status: str | None = None
    canary_passed: bool | None = None
    enqueued_task_ids: list[str] | None = None


class ReplicationGroupStatus(BaseModel):
    group_id: str
    task_type: str
    capability_required: str
    payload: dict[str, Any]
    slots: int
    quorum: int
    status: str
    winning_result: dict[str, Any] | None = None
    created_at: str
    resolved_at: str | None = None
    tasks: list[dict[str, Any]]
    submissions: list[dict[str, Any]]
    fingerprint_counts: dict[str, int]


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


class CredibilityImportRequest(BaseModel):
    source_project_id: str
    target_project_id: str
    capabilities: list[str] | None = None


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
