from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from agentswarm_platform.auth import OwnerAuth, resolve_owner_auth
from agentswarm_platform.budgets import (
    is_budget_exceeded_error,
    is_quarantine_error,
    resolve_egress_allowlist,
    resolve_resource_budget,
    validate_egress_allowlist,
    validate_egress_for_capabilities,
)
from agentswarm_platform.capabilities import (
    validate_capabilities,
    validate_version_signature,
)
from agentswarm_platform.deps import bind_store
from agentswarm_platform.models import (
    AgentBudgetStatus,
    AgentPresenceRequest,
    AgentPresenceResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AssignmentEnvelope,
    AgentCreditsResponse,
    AuditEvent,
    CheckpointRequest,
    ClaimRequest,
    ClaimResponse,
    CreativeGoalRequest,
    CreativeGoalResponse,
    GitArtifactEnvelope,
    GitPatchRequest,
    ReplicationGroupStatus,
    CredibilityImportRequest,
    DeployCreateRequest,
    DeployRequestEnvelope,
    GovernanceTemplateEnvelope,
    GovernanceTemplateSummary,
    PoolNeedRequest,
    PoolNeedResponse,
    ProjectCreateRequest,
    ProjectEnvelope,
    ProjectRepoConfigRequest,
    SubmitRequest,
    SubmitResponse,
    TaskCreateRequest,
    TaskEnvelope,
    VerificationEnvelope,
    VerifyRequest,
)
from agentswarm_platform.platform_models import MemoryUpsertRequest, PlatformSummary
from agentswarm_platform.oauth import router as auth_router
from agentswarm_platform.assignment_config import assignment_mode
from agentswarm_platform.store import Store

DB_PATH = Path(os.environ.get("AGENTSWARM_DB", "platform/data/agentswarm.db"))
store = Store(DB_PATH)
bind_store(store)

app = FastAPI(
    title="AgentSwarm Task Pool",
    version="0.1.0",
    description="Phase 0 pull-based task pool per ROADMAP.md §6.2",
)

app.include_router(auth_router)


def get_owner(
    authorization: Annotated[str | None, Header()] = None,
    x_bootstrap_token: Annotated[str | None, Header()] = None,
) -> OwnerAuth:
    return resolve_owner_auth(authorization, x_bootstrap_token)


@app.get("/capabilities")
def list_capabilities() -> dict:
    from agentswarm_platform.capabilities import load_capability_registry

    return load_capability_registry()


@app.get("/governance/templates", response_model=list[GovernanceTemplateSummary])
def list_governance_templates() -> list[GovernanceTemplateSummary]:
    from agentswarm_platform.governance_templates import list_governance_templates

    return [GovernanceTemplateSummary(**item) for item in list_governance_templates()]


@app.get("/governance/templates/{template_id}", response_model=GovernanceTemplateEnvelope)
def get_governance_template(template_id: str) -> GovernanceTemplateEnvelope:
    from agentswarm_platform.governance_templates import get_governance_template

    template = get_governance_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="governance template not found")
    return GovernanceTemplateEnvelope(**template)


@app.get("/projects", response_model=list[ProjectEnvelope])
def list_projects() -> list[ProjectEnvelope]:
    return [ProjectEnvelope(**project) for project in store.list_projects()]


@app.post("/projects", response_model=ProjectEnvelope)
def create_project(
    body: ProjectCreateRequest,
    owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> ProjectEnvelope:
    try:
        project = store.create_project(
            name=body.name,
            description=body.description,
            project_id=body.project_id,
            governance_template_id=body.governance_template_id,
            actor_id=None if owner.via_bootstrap else owner.owner_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectEnvelope(**project)


@app.get("/projects/{project_id}", response_model=ProjectEnvelope)
def get_project(project_id: str) -> ProjectEnvelope:
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectEnvelope(**project)


@app.patch("/projects/{project_id}/repo", response_model=ProjectEnvelope)
def configure_project_repo(
    project_id: str,
    body: ProjectRepoConfigRequest,
    owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> ProjectEnvelope:
    try:
        project = store.update_project_repo_config(
            project_id,
            repo_url=body.repo_url,
            default_branch=body.default_branch,
            forge_type=body.forge_type,
            actor_id=None if owner.via_bootstrap else owner.owner_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectEnvelope(**project)


@app.post("/projects/{project_id}/git/patches")
def create_git_patch_assignment(
    project_id: str,
    body: GitPatchRequest,
    _owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> dict:
    try:
        return store.create_git_patch_assignment(
            project_id=project_id,
            patch=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/{project_id}/governance")
def get_project_governance(project_id: str) -> dict:
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {
        "project_id": project["project_id"],
        "governance_template_id": project.get("governance_template_id"),
        "governance_config": project.get("governance_config") or {},
    }


@app.get("/moderation/flags")
def list_moderation_flags(
    status: str | None = Query(default="open"),
    limit: int = Query(default=50, le=200),
) -> dict:
    return {"flags": store.list_moderation_flags(status=status, limit=limit)}


@app.get("/platform/summary", response_model=PlatformSummary)
def platform_summary() -> PlatformSummary:
    return PlatformSummary(**store.get_platform_summary())


@app.get("/memory")
def list_memory() -> dict:
    return {"entries": store.list_memory()}


@app.get("/memory/{memory_key}")
def get_memory_entry(memory_key: str) -> dict:
    entry = store.get_memory(memory_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="memory key not found")
    return entry


@app.put("/memory/{memory_key}")
def put_memory_entry(
    memory_key: str,
    body: MemoryUpsertRequest,
    authorization: Annotated[str | None, Header()] = None,
    x_bootstrap_token: Annotated[str | None, Header()] = None,
) -> dict:
    from agentswarm_platform.auth import auth_enforced

    if body.key != memory_key:
        raise HTTPException(status_code=400, detail="key in body must match path")

    if body.agent_id is not None or body.signature is not None:
        if not body.agent_id or not body.signature:
            raise HTTPException(
                status_code=400,
                detail="agent memory write requires agent_id and signature",
            )
        try:
            return store.upsert_memory_by_agent(
                memory_key=memory_key,
                content=body.content,
                tags=body.tags,
                agent_id=body.agent_id,
                signature=body.signature,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if auth_enforced():
        owner = resolve_owner_auth(authorization, x_bootstrap_token)
        updated_by = owner.github_login
    else:
        updated_by = resolve_owner_auth(authorization, x_bootstrap_token).github_login

    return store.upsert_memory(
        memory_key=memory_key,
        content=body.content,
        tags=body.tags,
        updated_by=updated_by,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/platform/config")
def platform_config() -> dict[str, object]:
    from agentswarm_platform.auth import public_parameters as auth_parameters
    from agentswarm_platform.credibility import public_parameters
    from agentswarm_platform.agent_versioning import versioning_public_parameters
    from agentswarm_platform.version_probation import public_parameters as version_parameters

    return {
        "assignment_mode": assignment_mode(),
        "auth": auth_parameters(),
        "credibility": public_parameters(),
        "versioning": {**versioning_public_parameters(), **version_parameters()},
    }


@app.post("/agents/register", response_model=AgentRegisterResponse)
def register_agent(
    body: AgentRegisterRequest,
    owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> AgentRegisterResponse:
    try:
        validate_capabilities(body.capabilities)
        validate_version_signature(body.version_signature)
        validate_egress_for_capabilities(body.capabilities, body.egress_allowlist)
        if body.egress_allowlist is not None:
            validate_egress_allowlist(body.egress_allowlist)
        resource_budget = resolve_resource_budget(
            body.capabilities, body.resource_budget
        ).as_dict()
        egress_allowlist = resolve_egress_allowlist(
            body.capabilities, body.egress_allowlist
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    owner_label = owner.github_login
    if not owner.via_bootstrap and body.owner and body.owner != owner.github_login:
        raise HTTPException(status_code=400, detail="owner field must match authenticated login")
    try:
        return store.register_agent(
            public_key=body.public_key,
            owner=owner_label,
            capabilities=body.capabilities,
            version_signature=body.version_signature,
            owner_id=None if owner.via_bootstrap and owner.github_login == "bootstrap" else owner.owner_id,
            resource_budget=resource_budget,
            egress_allowlist=egress_allowlist,
            project_ids=body.project_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/agents/{agent_id}/budget", response_model=AgentBudgetStatus)
def get_agent_budget(agent_id: str) -> AgentBudgetStatus:
    status = store.get_agent_budget_status(agent_id)
    if status is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return status


@app.get("/agents/{agent_id}/credibility")
def get_agent_credibility(
    agent_id: str,
    project_id: str = Query(default="default"),
) -> dict:
    scores = store.get_agent_credibility(agent_id, project_id=project_id)
    if scores is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent_id": agent_id, "project_id": project_id, "capabilities": scores}


@app.get("/agents/{agent_id}/credits", response_model=AgentCreditsResponse)
def get_agent_credits(agent_id: str) -> AgentCreditsResponse:
    credits = store.get_agent_credits(agent_id)
    if credits is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return AgentCreditsResponse(**credits)


@app.get("/agents/{agent_id}/profile")
def get_agent_profile(
    agent_id: str,
    project_id: str = Query(default="default"),
) -> dict:
    profile = store.get_agent_profile(agent_id, project_id=project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return profile


@app.post("/agents/{agent_id}/presence", response_model=AgentPresenceResponse)
def record_agent_presence(agent_id: str, body: AgentPresenceRequest) -> AgentPresenceResponse:
    try:
        recorded = store.record_agent_presence(
            agent_id,
            status=body.status,
            capabilities=body.capabilities,
            model_id=body.model_id,
            load=body.load,
            client_version=body.client_version,
            ttl_sec=body.ttl_sec,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AgentPresenceResponse(**recorded)


@app.get("/agents/{agent_id}/assignments/pending", response_model=AssignmentEnvelope | None)
def get_pending_assignment(agent_id: str) -> AssignmentEnvelope | None:
    assignment = store.get_pending_assignment(agent_id)
    if assignment is None:
        return None
    return AssignmentEnvelope(
        lease_id=assignment["lease_id"],
        task_id=assignment["task_id"],
        task_type=assignment["task_type"],
        capability_required=assignment["capability_required"],
        project_id=assignment["project_id"],
        claim_token=assignment["claim_token"],
        expires_at=assignment["expires_at"],
        assignment_signature=assignment["assignment_signature"],
        capsule=assignment.get("capsule") or {},
    )


@app.post("/pool/need", response_model=PoolNeedResponse)
def request_pool_need(
    body: PoolNeedRequest,
    _owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> PoolNeedResponse:
    try:
        result = store.request_pool_need(
            role=body.role,
            capability_required=body.capability_required,
            parent_task_id=body.parent_task_id,
            task_id=body.task_id,
            project_id=body.project_id,
            task_type=body.task_type,
            payload=body.payload,
            constraints=body.constraints,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PoolNeedResponse(**result)


@app.post("/creative/goals", response_model=CreativeGoalResponse)
def create_creative_goal(
    body: CreativeGoalRequest,
    _owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> CreativeGoalResponse:
    try:
        result = store.create_creative_goal(
            poster_agent_id=body.poster_agent_id,
            brief=body.brief,
            rubric=body.rubric,
            project_id=body.project_id,
            min_reviewers=body.min_reviewers,
            pass_threshold=body.pass_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreativeGoalResponse(**result)


@app.get("/creative/goals/{goal_id}")
def get_creative_goal(goal_id: str) -> dict:
    goal = store.get_creative_goal_status(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal not found")
    return goal


@app.get("/agents/{agent_id}/canary-stats")
def get_agent_canary_stats(agent_id: str) -> dict:
    stats = store.get_agent_canary_stats(agent_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return stats


@app.get("/replication/{group_id}", response_model=ReplicationGroupStatus)
def get_replication_group(group_id: str) -> ReplicationGroupStatus:
    status = store.get_replication_group_status(group_id)
    if status is None:
        raise HTTPException(status_code=404, detail="replication group not found")
    return ReplicationGroupStatus(**status)


@app.get("/credibility/transfer-rules")
def credibility_transfer_rules() -> dict:
    from agentswarm_platform.credibility_transfer import transfer_rules

    return transfer_rules()


@app.post("/agents/{agent_id}/credibility/import")
def import_agent_credibility(
    agent_id: str,
    body: CredibilityImportRequest,
    _owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> dict:
    try:
        imports = store.import_agent_credibility(
            agent_id=agent_id,
            source_project_id=body.source_project_id,
            target_project_id=body.target_project_id,
            capabilities=body.capabilities,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"agent_id": agent_id, "imports": imports}


@app.post("/credibility/apply-decay")
def apply_credibility_decay(
    _owner: Annotated[OwnerAuth, Depends(get_owner)],
    project_id: str | None = Query(default=None),
) -> dict:
    return store.apply_credibility_decay(project_id=project_id)


@app.get("/owners/{owner_id}/anchoring")
def get_owner_anchoring(owner_id: str) -> dict:
    summary = store.get_owner_anchoring(owner_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="owner not found")
    return summary


@app.post("/deploy/requests", response_model=DeployRequestEnvelope)
def create_deploy_request(
    body: DeployCreateRequest,
    owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> DeployRequestEnvelope:
    if owner.via_bootstrap and owner.owner_id is None:
        raise HTTPException(status_code=400, detail="deploy requests require verified owner")
    try:
        request = store.create_deploy_request(
            project_id=body.project_id,
            environment=body.environment,
            artifact_ref=body.artifact_ref,
            description=body.description,
            owner_id=owner.owner_id or owner.github_login,
            required_signoffs=body.required_signoffs,
            min_credibility=body.min_credibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeployRequestEnvelope(**request)


@app.get("/deploy/requests", response_model=list[DeployRequestEnvelope])
def list_deploy_requests(
    status: Annotated[str | None, Query()] = None,
    project_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[DeployRequestEnvelope]:
    rows = store.list_deploy_requests(status=status, project_id=project_id, limit=limit)
    return [DeployRequestEnvelope(**row) for row in rows]


@app.get("/deploy/requests/{request_id}", response_model=DeployRequestEnvelope)
def get_deploy_request(request_id: str) -> DeployRequestEnvelope:
    request = store.get_deploy_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="deploy request not found")
    return DeployRequestEnvelope(**request)


@app.get("/credibility/leaderboard")
def get_credibility_leaderboard(
    capability: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    project_id: str = Query(default="default"),
) -> dict:
    return {
        "capability": capability,
        "project_id": project_id,
        "entries": store.get_credibility_leaderboard(capability, limit, project_id),
    }


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict:
    agent = store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


@app.get("/agents/{agent_id}/versions")
def get_agent_versions(agent_id: str) -> dict:
    versions = store.get_agent_versions(agent_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent_id": agent_id, "versions": versions}


@app.post("/tasks", response_model=TaskEnvelope)
def create_task(
    body: TaskCreateRequest,
    _owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> TaskEnvelope:
    try:
        return store.create_task(
            task_type=body.task_type,
            capability_required=body.capability_required,
            payload=body.payload,
            parent_task_id=body.parent_task_id,
            parent_submission_id=body.parent_submission_id,
            project_id=body.project_id,
            assignment_only=body.assignment_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/submissions/{submission_id}/git-artifact", response_model=GitArtifactEnvelope)
def get_submission_git_artifact(submission_id: str) -> GitArtifactEnvelope:
    artifact = store.get_submission_git_artifact(submission_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="git artifact not found")
    return GitArtifactEnvelope(**artifact)


@app.get("/tasks/poll", response_model=list[TaskEnvelope])
def poll_tasks(
    agent_id: str = Query(...),
    capability: str | None = Query(default=None),
) -> list[TaskEnvelope]:
    return store.poll_tasks(agent_id, capability)


@app.post("/tasks/checkpoint")
def checkpoint(body: CheckpointRequest) -> dict[str, str]:
    try:
        store.checkpoint(body.claim_token, body.partial_state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ack"}


@app.post("/tasks/submit", response_model=SubmitResponse)
def submit_task(body: SubmitRequest) -> SubmitResponse:
    try:
        task_type = store.get_task_type_by_claim_token(body.claim_token)
        if task_type is None:
            raise ValueError("invalid claim token")
        if task_type == "tester.run":
            return store.complete_tester_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "reviewer.approve":
            return store.complete_reviewer_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "planner.plan":
            return store.complete_planner_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "orchestrator.scan":
            return store.complete_orchestrator_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "moderator.scan":
            return store.complete_moderator_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "deploy.approve":
            return store.complete_deploy_approve_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "deploy.execute":
            return store.complete_deploy_execute_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "coordinator.decompose":
            return store.complete_coordinator_decompose_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "creative.text":
            return store.complete_creative_text_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "reviewer.subjective":
            return store.complete_reviewer_subjective_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "scraper.fetch":
            return store.complete_scraper_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "summarizer.summarize":
            return store.complete_summarizer_submit(
                body.claim_token, body.result, body.signature
            )
        if task_type == "classifier.label":
            payload = store.get_task_payload_by_claim_token(body.claim_token) or {}
            if payload.get("pipeline"):
                return store.complete_classifier_pipeline_submit(
                    body.claim_token, body.result, body.signature
                )
        return store.submit_task(body.claim_token, body.result, body.signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/tasks/{task_id}", response_model=TaskEnvelope)
def get_task(task_id: str) -> TaskEnvelope:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.post("/tasks/{task_id}/claim", response_model=ClaimResponse)
def claim_task(task_id: str, body: ClaimRequest) -> ClaimResponse:
    try:
        return store.claim_task(task_id, body.agent_id)
    except ValueError as exc:
        if is_budget_exceeded_error(str(exc)):
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        if is_quarantine_error(str(exc)):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/verifications/poll", response_model=list[VerificationEnvelope])
def poll_verifications(agent_id: str = Query(...)) -> list[VerificationEnvelope]:
    return store.poll_verifications(agent_id)


@app.post("/verifications/verify")
def verify(body: VerifyRequest) -> dict[str, str]:
    try:
        store.verify_submission(
            body.claim_token, body.verdict, body.notes, body.signature
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ack"}


@app.post("/verifications/{verification_id}/claim", response_model=ClaimResponse)
def claim_verification(verification_id: str, body: ClaimRequest) -> ClaimResponse:
    try:
        return store.claim_verification(verification_id, body.agent_id)
    except ValueError as exc:
        if is_budget_exceeded_error(str(exc)):
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/audit", response_model=list[AuditEvent])
def audit_log(limit: int = Query(default=50, le=200)) -> list[AuditEvent]:
    return store.list_audit_events(limit)
