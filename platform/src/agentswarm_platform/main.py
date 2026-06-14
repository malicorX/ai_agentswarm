from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from agentswarm_platform.models import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AuditEvent,
    CheckpointRequest,
    ClaimRequest,
    ClaimResponse,
    SubmitRequest,
    SubmitResponse,
    TaskCreateRequest,
    TaskEnvelope,
    VerificationEnvelope,
    VerifyRequest,
)
from agentswarm_platform.store import Store

DB_PATH = Path(os.environ.get("AGENTSWARM_DB", "platform/data/agentswarm.db"))
store = Store(DB_PATH)

app = FastAPI(
    title="AgentSwarm Task Pool",
    version="0.1.0",
    description="Phase 0 pull-based task pool per ROADMAP.md §6.2",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agents/register", response_model=AgentRegisterResponse)
def register_agent(body: AgentRegisterRequest) -> AgentRegisterResponse:
    return store.register_agent(
        public_key=body.public_key,
        owner=body.owner,
        capabilities=body.capabilities,
        version_signature=body.version_signature,
    )


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict:
    agent = store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


@app.post("/tasks", response_model=TaskEnvelope)
def create_task(body: TaskCreateRequest) -> TaskEnvelope:
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/audit", response_model=list[AuditEvent])
def audit_log(limit: int = Query(default=50, le=200)) -> list[AuditEvent]:
    return store.list_audit_events(limit)
