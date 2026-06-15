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
    assignment_only: bool = False


class ProjectCreateRequest(BaseModel):
    project_id: str | None = None
    name: str
    description: str | None = None
    governance_template_id: str | None = None


class ProjectEnvelope(BaseModel):
    project_id: str
    name: str
    description: str | None = None
    created_at: str
    governance_template_id: str | None = None
    governance_config: dict[str, Any] = Field(default_factory=dict)
    repo_url: str | None = None
    default_branch: str = "main"
    forge_type: str = "git"


class ProjectRepoConfigRequest(BaseModel):
    repo_url: str
    default_branch: str = "main"
    forge_type: str = "git"


class GitPatchRequest(BaseModel):
    file: str
    insert: str = ""
    marker: str = "<!-- agentswarm -->"


class GitArtifactEnvelope(BaseModel):
    submission_id: str
    task_id: str
    project_id: str
    repo_url: str
    branch: str
    commit_sha: str
    forge_type: str
    created_at: str


class GovernanceTemplateSummary(BaseModel):
    template_id: str
    name: str
    description: str | None = None


class GovernanceTemplateEnvelope(GovernanceTemplateSummary):
    defaults: dict[str, Any] = Field(default_factory=dict)


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
    parallel_kind: str = "replication"
    good_attempt_mint: float = 0.0
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


class DeployCreateRequest(BaseModel):
    project_id: str = "default"
    environment: str
    artifact_ref: str
    description: str | None = None
    required_signoffs: int | None = None
    min_credibility: float | None = None


class DeployRequestEnvelope(BaseModel):
    request_id: str
    project_id: str
    environment: str
    artifact_ref: str
    description: str | None = None
    status: str
    required_signoffs: int
    min_credibility: float
    signoff_count: int
    signoffs: list[dict[str, Any]] = Field(default_factory=list)
    approve_task_ids: list[str] | None = None
    execute_task_id: str | None = None
    created_at: str
    created_by_owner_id: str
    approved_at: str | None = None
    deployed_at: str | None = None
    executed_by_agent_id: str | None = None
    execution_result: dict[str, Any] | None = None


class AuditEvent(BaseModel):
    seq: int
    timestamp: str
    event_type: str
    actor_id: str | None
    details: dict[str, Any]
    prev_hash: str
    entry_hash: str


class AgentPresenceRequest(BaseModel):
    status: str = "idle"
    capabilities: list[str]
    model_id: str | None = None
    load: float = 0.0
    client_version: str | None = None
    ttl_sec: int = 60


class AgentPresenceResponse(BaseModel):
    agent_id: str
    status: str
    capabilities: list[str]
    model_id: str | None = None
    load: float
    client_version: str | None = None
    ttl_sec: int
    last_seen_at: str


class PoolNeedRequest(BaseModel):
    role: str
    capability_required: str
    parent_task_id: str | None = None
    task_id: str | None = None
    project_id: str = "default"
    task_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class PoolNeedResponse(BaseModel):
    need_id: str
    task_id: str
    assigned: bool
    assignment: dict[str, Any] | None = None


class AssignmentEnvelope(BaseModel):
    lease_id: str
    task_id: str
    task_type: str
    capability_required: str
    project_id: str
    claim_token: str
    expires_at: str
    assignment_signature: str
    capsule: dict[str, Any] = Field(default_factory=dict)


class CreativeGoalRequest(BaseModel):
    poster_agent_id: str
    brief: str
    rubric: list[dict[str, Any]]
    project_id: str = "default"
    min_reviewers: int = 3
    pass_threshold: float = 6.0
    difficulty: float = Field(default=1.0, ge=0.1, le=10.0)


class CreativeGoalResponse(BaseModel):
    goal_id: str
    coordinator_task_id: str
    status: str


class CreativeGoalAppealRequest(BaseModel):
    filed_by_agent_id: str
    message: str = Field(min_length=10, max_length=4000)


class CreativeGoalAppealResolveRequest(BaseModel):
    decision: str
    resolution_note: str | None = None


class CreativeGoalAppealResponse(BaseModel):
    appeal_id: str
    goal_id: str
    status: str


class AgentCreditsResponse(BaseModel):
    agent_id: str
    balance: float
    enabled: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
