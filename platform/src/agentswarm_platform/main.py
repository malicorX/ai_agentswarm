from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from agentswarm_platform.auth import OwnerAuth, resolve_owner_auth
from agentswarm_platform.budgets import (
    is_budget_exceeded_error,
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
    AgentRegisterRequest,
    AgentRegisterResponse,
    AuditEvent,
    CheckpointRequest,
    ClaimRequest,
    ClaimResponse,
    ReplicationGroupStatus,
    SubmitRequest,
    SubmitResponse,
    TaskCreateRequest,
    TaskEnvelope,
    VerificationEnvelope,
    VerifyRequest,
)
from agentswarm_platform.platform_models import MemoryUpsertRequest, PlatformSummary
from agentswarm_platform.oauth import router as auth_router
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
    owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> dict:
    if body.key != memory_key:
        raise HTTPException(status_code=400, detail="key in body must match path")
    return store.upsert_memory(
        memory_key=memory_key,
        content=body.content,
        tags=body.tags,
        updated_by=owner.github_login,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    return store.register_agent(
        public_key=body.public_key,
        owner=owner_label,
        capabilities=body.capabilities,
        version_signature=body.version_signature,
        owner_id=None if owner.via_bootstrap and owner.github_login == "bootstrap" else owner.owner_id,
        resource_budget=resource_budget,
        egress_allowlist=egress_allowlist,
    )


@app.get("/agents/{agent_id}/budget", response_model=AgentBudgetStatus)
def get_agent_budget(agent_id: str) -> AgentBudgetStatus:
    status = store.get_agent_budget_status(agent_id)
    if status is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return status


@app.get("/agents/{agent_id}/credibility")
def get_agent_credibility(agent_id: str) -> dict:
    scores = store.get_agent_credibility(agent_id)
    if scores is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent_id": agent_id, "capabilities": scores}


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


@app.get("/credibility/leaderboard")
def get_credibility_leaderboard(
    capability: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> dict:
    return {
        "capability": capability,
        "entries": store.get_credibility_leaderboard(capability, limit),
    }


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict:
    agent = store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


@app.post("/tasks", response_model=TaskEnvelope)
def create_task(
    body: TaskCreateRequest,
    _owner: Annotated[OwnerAuth, Depends(get_owner)],
) -> TaskEnvelope:
    return store.create_task(
        task_type=body.task_type,
        capability_required=body.capability_required,
        payload=body.payload,
        parent_task_id=body.parent_task_id,
        parent_submission_id=body.parent_submission_id,
    )


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
