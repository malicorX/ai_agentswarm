from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from agentswarm_platform.budgets import (
    default_budget_for_capabilities,
    default_egress_for_capabilities,
    resolve_egress_allowlist,
    resolve_resource_budget,
)
from agentswarm_platform.memory_policy import assert_agent_memory_write_allowed
from agentswarm_platform.memory_store import (
    ensure_memory_schema,
    get_memory_entry,
    list_memory_entries,
    upsert_memory_entry,
)
from agentswarm_platform.moderation_store import (
    apply_moderator_action,
    ensure_moderation_schema,
    is_agent_quarantined,
    list_moderation_flags,
)
from agentswarm_platform.owner_anchoring import owner_anchoring_summary
from agentswarm_platform.owner_analytics import summarize_owner_clusters
from agentswarm_platform.project_bootstrap import apply_project_bootstrap
from agentswarm_platform.project_store import (
    DEFAULT_PROJECT_ID,
    agent_project_ids,
    create_project as create_project_row,
    ensure_projects_schema,
    get_project,
    join_agent_to_project,
    list_projects,
    update_project_repo,
    validate_project_id,
)
from agentswarm_platform.orchestration import enqueue_child_tasks
from agentswarm_platform.canary_store import ensure_canary_schema, evaluate_canary, get_canary_stats
from agentswarm_platform.deploy_policy import (
    DeployPolicy,
    resolve_deploy_policy,
    resolve_deploy_policy_for_environment,
)
from agentswarm_platform.deploy_store import (
    assert_deploy_signoff_allowed,
    enqueue_deploy_approve_tasks,
    ensure_deploy_schema,
    get_deploy_request as get_deploy_request_row,
    insert_deploy_request,
    list_deploy_requests as list_deploy_request_rows,
    record_deploy_execution,
    record_deploy_signoff,
    refresh_deploy_request_status,
    reject_deploy_request,
    summarize_deploy_requests,
)
from agentswarm_platform.replication import (
    ReplicationConfig,
    parse_replication_config,
    shared_replication_payload,
)
from agentswarm_platform.replication_store import (
    agent_already_in_group,
    ensure_replication_schema,
    get_replication_group,
    record_replication_submit,
)
from agentswarm_platform.credibility_ledger import (
    apply_inactivity_decay_all,
    apply_major_version_haircut,
    apply_task_outcome,
    assert_claim_tier_allowed,
    agent_can_claim_by_tier,
    ensure_credibility_schema,
    import_cross_project_credibility,
    leaderboard as credibility_leaderboard,
    list_agent_credibility,
    lock_claim_stake,
    project_id_from_task_row,
    seed_agent_capabilities,
)
from agentswarm_platform.credibility import credibility_enabled
from agentswarm_platform.agent_versioning import assert_version_reconnect_allowed, classify_version_bump
from agentswarm_platform.version_store import list_agent_versions, record_version_entry
from agentswarm_platform.assignment_config import dispatch_enabled
from agentswarm_platform.presence_store import (
    ensure_presence_schema,
    set_presence_status,
    upsert_presence,
)
from agentswarm_platform.dispatch_store import (
    create_assignment_lease,
    ensure_dispatch_schema,
    get_pending_assignment_for_agent,
    get_pool_need,
    insert_pool_need,
    mark_need_assigned,
    new_claim_token,
)
from agentswarm_platform.dispatcher import dispatch_pool_need as pick_dispatch_agent
from agentswarm_platform.git_store import (
    ensure_git_schema,
    get_git_artifact,
    insert_git_artifact,
)
from agentswarm_platform.credits_ledger import (
    burn_credits,
    credits_enabled,
    ensure_credits_schema,
    get_credits_balance,
    mint_credits,
)
from agentswarm_platform.credit_pricing import post_cost, reviewer_reward_for
from agentswarm_platform.coordinator_plan import (
    build_default_creative_goal_plan,
    materialize_deferred_payload,
    resolve_pool_need_constraints,
    validate_coordinator_plan,
)
from agentswarm_platform.subjective_store import (
    aggregate_quorum,
    clear_goal_deferred_pool_needs,
    ensure_subjective_schema,
    get_creative_goal,
    insert_creative_goal,
    insert_subjective_review,
    list_reviews_for_goal,
    resolve_goal,
    set_goal_artifact,
    set_goal_deferred_pool_needs,
    weighted_review_score,
)
from agentswarm_platform.models import (
    AgentBudgetStatus,
    AgentBudgetUsage,
    AgentRegisterResponse,
    AuditEvent,
    ClaimResponse,
    SubmitResponse,
    TaskEnvelope,
    TaskStatus,
    VerificationEnvelope,
    VerificationStatus,
    utc_now_iso,
)


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL UNIQUE,
                    owner TEXT NOT NULL,
                    capabilities TEXT NOT NULL,
                    version_signature TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    capability_required TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    parent_task_id TEXT,
                    parent_submission_id TEXT,
                    claimed_by TEXT,
                    claim_token TEXT,
                    claim_deadline TEXT,
                    created_at TEXT NOT NULL,
                    submitted_at TEXT,
                    submission_id TEXT,
                    submission_result TEXT,
                    submission_signature TEXT
                );

                CREATE TABLE IF NOT EXISTS verifications (
                    verification_id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_summary TEXT NOT NULL,
                    claimed_by TEXT,
                    claim_token TEXT,
                    claim_deadline TEXT,
                    verdict TEXT,
                    verdict_notes TEXT,
                    verdict_signature TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_id TEXT,
                    details TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL
                );
                """
            )
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS owners (
                owner_id TEXT PRIMARY KEY,
                github_user_id TEXT NOT NULL UNIQUE,
                github_login TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()
        }
        if "owner_id" not in columns:
            conn.execute("ALTER TABLE agents ADD COLUMN owner_id TEXT")
        if "resource_budget" not in columns:
            conn.execute("ALTER TABLE agents ADD COLUMN resource_budget TEXT")
        if "egress_allowlist" not in columns:
            conn.execute("ALTER TABLE agents ADD COLUMN egress_allowlist TEXT")
        task_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "project_id" not in task_columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN project_id TEXT NOT NULL DEFAULT 'default'"
            )
        if "assignment_only" not in task_columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN assignment_only INTEGER NOT NULL DEFAULT 0"
            )
        ensure_presence_schema(conn)
        ensure_dispatch_schema(conn)
        ensure_projects_schema(conn)
        ensure_credibility_schema(conn)
        ensure_replication_schema(conn)
        ensure_canary_schema(conn)
        ensure_memory_schema(conn)
        ensure_moderation_schema(conn)
        from agentswarm_platform.owner_anchoring import ensure_owner_anchoring_schema

        ensure_owner_anchoring_schema(conn)
        ensure_deploy_schema(conn)
        ensure_credits_schema(conn)
        ensure_subjective_schema(conn)
        ensure_git_schema(conn)
        from agentswarm_platform.version_store import ensure_version_schema
        from agentswarm_platform.version_probation import ensure_probation_schema

        ensure_version_schema(conn)
        ensure_probation_schema(conn)

    def upsert_owner(self, github_user_id: str, github_login: str) -> dict[str, Any]:
        from agentswarm_platform.auth import new_owner_id

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM owners WHERE github_user_id = ?", (github_user_id,)
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE owners SET github_login = ? WHERE owner_id = ?",
                    (github_login, row["owner_id"]),
                )
                return {
                    "owner_id": row["owner_id"],
                    "github_user_id": github_user_id,
                    "github_login": github_login,
                }
            owner_id = new_owner_id()
            created_at = utc_now_iso()
            conn.execute(
                """
                INSERT INTO owners (owner_id, github_user_id, github_login, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (owner_id, github_user_id, github_login, created_at),
            )
            self._append_audit(
                conn,
                "owner.registered",
                owner_id,
                {"github_user_id": github_user_id, "github_login": github_login},
            )
            return {
                "owner_id": owner_id,
                "github_user_id": github_user_id,
                "github_login": github_login,
            }

    def _append_audit(
        self,
        conn: sqlite3.Connection,
        event_type: str,
        actor_id: str | None,
        details: dict[str, Any],
    ) -> None:
        row = conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev_hash = row["entry_hash"] if row else "0" * 64
        timestamp = utc_now_iso()
        body = json.dumps(
            {
                "timestamp": timestamp,
                "event_type": event_type,
                "actor_id": actor_id,
                "details": details,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        entry_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT INTO audit_log (timestamp, event_type, actor_id, details, prev_hash, entry_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (timestamp, event_type, actor_id, json.dumps(details), prev_hash, entry_hash),
        )

    def register_agent(
        self,
        public_key: str,
        owner: str,
        capabilities: list[str],
        version_signature: str,
        *,
        owner_id: str | None = None,
        resource_budget: dict[str, int] | None = None,
        egress_allowlist: list[str] | None = None,
        project_ids: list[str] | None = None,
    ) -> AgentRegisterResponse:
        credential = secrets.token_urlsafe(24)
        budget_json = json.dumps(resource_budget) if resource_budget is not None else None
        egress_json = json.dumps(egress_allowlist) if egress_allowlist is not None else None
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT agent_id, version_signature FROM agents WHERE public_key = ?",
                (public_key,),
            ).fetchone()
            if existing is not None:
                agent_id = existing["agent_id"]
                previous_version = str(existing["version_signature"])
                assert_version_reconnect_allowed(previous_version, version_signature)
                conn.execute(
                    """
                    UPDATE agents
                    SET owner = ?, owner_id = ?, capabilities = ?, version_signature = ?,
                        resource_budget = COALESCE(?, resource_budget),
                        egress_allowlist = COALESCE(?, egress_allowlist)
                    WHERE agent_id = ?
                    """,
                    (
                        owner,
                        owner_id,
                        json.dumps(capabilities),
                        version_signature,
                        budget_json,
                        egress_json,
                        agent_id,
                    ),
                )
                bump = classify_version_bump(previous_version, version_signature)
                if bump is not None:
                    record_version_entry(
                        conn,
                        agent_id=agent_id,
                        version_signature=version_signature,
                        bump_kind=bump,
                        previous_version=previous_version,
                    )
                    if bump == "major":
                        apply_major_version_haircut(conn, agent_id)
                        from agentswarm_platform.version_probation import (
                            start_major_version_probation,
                        )

                        probation_required = start_major_version_probation(conn, agent_id)
                        if probation_required > 0:
                            self._append_audit(
                                conn,
                                "agent.probation_started",
                                agent_id,
                                {
                                    "version_signature": version_signature,
                                    "verifications_required": probation_required,
                                },
                            )
                    self._append_audit(
                        conn,
                        "agent.version_bumped",
                        agent_id,
                        {
                            "previous_version": previous_version,
                            "version_signature": version_signature,
                            "bump_kind": bump,
                        },
                    )
                self._append_audit(
                    conn,
                    "agent.reconnected",
                    agent_id,
                    {
                        "owner": owner,
                        "owner_id": owner_id,
                        "capabilities": capabilities,
                        "version_signature": version_signature,
                    },
                )
                seed_agent_capabilities(conn, agent_id, capabilities)
                if project_ids is not None:
                    self._join_agent_projects(conn, agent_id, project_ids)
                    self._seed_credibility_for_projects(
                        conn, agent_id, capabilities, project_ids
                    )
                return AgentRegisterResponse(agent_id=agent_id, credential=credential)

            agent_id = f"agent_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, public_key, owner, owner_id, capabilities,
                    version_signature, created_at, resource_budget, egress_allowlist
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    public_key,
                    owner,
                    owner_id,
                    json.dumps(capabilities),
                    version_signature,
                    utc_now_iso(),
                    budget_json,
                    egress_json,
                ),
            )
            record_version_entry(
                conn,
                agent_id=agent_id,
                version_signature=version_signature,
                bump_kind="initial",
            )
            self._append_audit(
                conn,
                "agent.registered",
                agent_id,
                {
                    "owner": owner,
                    "owner_id": owner_id,
                    "capabilities": capabilities,
                    "version_signature": version_signature,
                },
            )
            self._join_agent_projects(conn, agent_id, project_ids)
            self._seed_credibility_for_projects(conn, agent_id, capabilities, project_ids)
        return AgentRegisterResponse(agent_id=agent_id, credential=credential)

    def get_agent_versions(self, agent_id: str) -> list[dict[str, Any]] | None:
        if self.get_agent(agent_id) is None:
            return None
        with self._conn() as conn:
            return list_agent_versions(conn, agent_id)

    def _project_targets(self, project_ids: list[str] | None) -> set[str]:
        if project_ids is None:
            return {DEFAULT_PROJECT_ID}
        targets = {validate_project_id(raw_id) for raw_id in project_ids}
        if not targets:
            return {DEFAULT_PROJECT_ID}
        return targets

    def _seed_credibility_for_projects(
        self,
        conn: sqlite3.Connection,
        agent_id: str,
        capabilities: list[str],
        project_ids: list[str] | None,
    ) -> None:
        for project_id in self._project_targets(project_ids):
            seed_agent_capabilities(conn, agent_id, capabilities, project_id)

    def _join_agent_projects(
        self,
        conn: sqlite3.Connection,
        agent_id: str,
        project_ids: list[str] | None,
    ) -> None:
        for project_id in self._project_targets(project_ids):
            join_agent_to_project(conn, agent_id, project_id)

    def create_project(
        self,
        *,
        name: str,
        description: str | None = None,
        project_id: str | None = None,
        governance_template_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            return create_project_row(
                conn,
                name=name,
                description=description,
                project_id=project_id,
                governance_template_id=governance_template_id,
                append_audit=self._append_audit,
                actor_id=actor_id,
                apply_bootstrap=apply_project_bootstrap,
            )

    def list_projects(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return list_projects(conn)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return get_project(conn, validate_project_id(project_id))

    def update_project_repo_config(
        self,
        project_id: str,
        *,
        repo_url: str,
        default_branch: str = "main",
        forge_type: str = "git",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        resolved = validate_project_id(project_id)
        with self._conn() as conn:
            return update_project_repo(
                conn,
                project_id=resolved,
                repo_url=repo_url,
                default_branch=default_branch,
                forge_type=forge_type,
                append_audit=self._append_audit,
                actor_id=actor_id,
            )

    def create_git_patch_assignment(
        self,
        *,
        project_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        if not dispatch_enabled():
            raise ValueError("git patch assignments require AGENTSWARM_ASSIGNMENT_MODE=dispatch")
        resolved = validate_project_id(project_id)
        project = self.get_project(resolved)
        if project is None:
            raise ValueError(f"unknown project: {resolved}")
        repo_url = project.get("repo_url")
        if not repo_url:
            raise ValueError("project repo_url is not configured")
        payload = {
            "capsule": {
                "git": {
                    "repo_url": repo_url,
                    "default_branch": project.get("default_branch") or "main",
                    "forge_type": project.get("forge_type") or "git",
                },
                "patch": patch,
            }
        }
        created = self.create_task(
            "codewriter.patch",
            "codewriter",
            payload,
            project_id=resolved,
            assignment_only=True,
        )
        need = self.request_pool_need(
            role="codewriter",
            capability_required="codewriter",
            parent_task_id=created.task_id,
            task_id=created.task_id,
            project_id=resolved,
            task_type="codewriter.patch",
            payload=payload,
            constraints={},
        )
        return {
            "task_id": created.task_id,
            "project_id": resolved,
            "assigned": need["assigned"],
            "assignment": need.get("assignment"),
        }

    def get_submission_git_artifact(self, submission_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return get_git_artifact(conn, submission_id)

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            return None
        keys = row.keys()
        return {
            "agent_id": row["agent_id"],
            "public_key": row["public_key"],
            "owner": row["owner"],
            "owner_id": row["owner_id"] if "owner_id" in keys else None,
            "capabilities": json.loads(row["capabilities"]),
            "version_signature": row["version_signature"],
            "resource_budget": self._agent_resource_budget(row),
            "egress_allowlist": self._agent_egress_allowlist(row),
            "quarantined": bool(row["quarantined"]) if "quarantined" in keys else False,
            "quarantine_reason": row["quarantine_reason"] if "quarantine_reason" in keys else None,
            "version_probation_remaining": (
                int(row["version_probation_remaining"])
                if "version_probation_remaining" in keys
                else 0
            ),
        }

    def _agent_resource_budget(self, row: sqlite3.Row) -> dict[str, int]:
        capabilities = json.loads(row["capabilities"])
        keys = row.keys()
        if "resource_budget" in keys and row["resource_budget"]:
            stored = json.loads(row["resource_budget"])
            return resolve_resource_budget(capabilities, stored).as_dict()
        return default_budget_for_capabilities(capabilities).as_dict()

    def _agent_egress_allowlist(self, row: sqlite3.Row) -> list[str]:
        capabilities = json.loads(row["capabilities"])
        keys = row.keys()
        if "egress_allowlist" in keys and row["egress_allowlist"]:
            stored = json.loads(row["egress_allowlist"])
            return resolve_egress_allowlist(capabilities, stored)
        return default_egress_for_capabilities(capabilities)

    def get_agent_budget_status(self, agent_id: str) -> AgentBudgetStatus | None:
        agent = self.get_agent(agent_id)
        if agent is None:
            return None
        usage = self._claim_usage(agent_id)
        return AgentBudgetStatus(
            agent_id=agent_id,
            resource_budget=agent["resource_budget"],
            egress_allowlist=agent["egress_allowlist"],
            usage=usage,
        )

    def _claim_usage(self, agent_id: str) -> AgentBudgetUsage:
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(
            microsecond=0
        ).isoformat()
        with self._conn() as conn:
            task_concurrent = conn.execute(
                """
                SELECT COUNT(*) AS n FROM tasks
                WHERE claimed_by = ? AND status = ?
                """,
                (agent_id, TaskStatus.CLAIMED.value),
            ).fetchone()["n"]
            verification_concurrent = conn.execute(
                """
                SELECT COUNT(*) AS n FROM verifications
                WHERE claimed_by = ? AND status = ? AND claim_token IS NOT NULL
                """,
                (agent_id, VerificationStatus.PENDING.value),
            ).fetchone()["n"]
            claims_last_hour = conn.execute(
                """
                SELECT COUNT(*) AS n FROM audit_log
                WHERE actor_id = ? AND event_type IN ('task.claimed', 'verification.claimed')
                  AND timestamp >= ?
                """,
                (agent_id, hour_ago),
            ).fetchone()["n"]
        return AgentBudgetUsage(
            concurrent_claims=int(task_concurrent) + int(verification_concurrent),
            claims_last_hour=int(claims_last_hour),
        )

    def _assert_claim_budget(self, conn: sqlite3.Connection, agent_id: str) -> None:
        agent_row = conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if agent_row is None:
            raise ValueError("unknown agent")
        budget = self._agent_resource_budget(agent_row)
        usage = self._claim_usage(agent_id)
        if usage.concurrent_claims >= budget["max_concurrent_claims"]:
            raise ValueError(
                "budget: concurrent claim limit exceeded "
                f"({usage.concurrent_claims}/{budget['max_concurrent_claims']})"
            )
        if usage.claims_last_hour >= budget["max_claims_per_hour"]:
            raise ValueError(
                "budget: hourly claim limit exceeded "
                f"({usage.claims_last_hour}/{budget['max_claims_per_hour']})"
            )

    def create_task(
        self,
        task_type: str,
        capability_required: str,
        payload: dict[str, Any],
        parent_task_id: str | None = None,
        parent_submission_id: str | None = None,
        project_id: str | None = None,
        *,
        assignment_only: bool = False,
    ) -> TaskEnvelope:
        resolved_project = validate_project_id(project_id or DEFAULT_PROJECT_ID)
        with self._conn() as conn:
            if get_project(conn, resolved_project) is None:
                raise ValueError(f"unknown project: {resolved_project}")
        replication = parse_replication_config(task_type, payload)
        if replication is not None:
            return self._create_replication_tasks(
                task_type=task_type,
                capability_required=capability_required,
                payload=payload,
                config=replication,
                project_id=resolved_project,
            )
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        created_at = utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, task_type, capability_required, status, payload,
                    parent_task_id, parent_submission_id, created_at, project_id,
                    assignment_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_type,
                    capability_required,
                    TaskStatus.CREATED.value,
                    json.dumps(payload),
                    parent_task_id,
                    parent_submission_id,
                    created_at,
                    resolved_project,
                    1 if assignment_only else 0,
                ),
            )
            self._append_audit(
                conn,
                "task.created",
                None,
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "capability_required": capability_required,
                    "project_id": resolved_project,
                },
            )
        return TaskEnvelope(
            task_id=task_id,
            task_type=task_type,
            capability_required=capability_required,
            status=TaskStatus.CREATED,
            payload=payload,
            created_at=created_at,
            parent_task_id=parent_task_id,
            project_id=resolved_project,
        )

    def _create_replication_tasks(
        self,
        *,
        task_type: str,
        capability_required: str,
        payload: dict[str, Any],
        config: ReplicationConfig,
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> TaskEnvelope:
        group_id = f"repl_{uuid.uuid4().hex[:12]}"
        created_at = utc_now_iso()
        shared = shared_replication_payload(payload)
        first_envelope: TaskEnvelope | None = None
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO replication_groups (
                    group_id, task_type, capability_required, payload,
                    slots, quorum, status, created_at, parallel_kind, good_attempt_mint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id,
                    task_type,
                    capability_required,
                    json.dumps(shared),
                    config.slots,
                    config.quorum,
                    "pending",
                    created_at,
                    config.kind,
                    config.good_attempt_mint,
                ),
            )
            for slot in range(config.slots):
                task_id = f"task_{uuid.uuid4().hex[:12]}"
                slot_payload = {
                    **shared,
                    "replication_group_id": group_id,
                    "replication_slot": slot,
                }
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, task_type, capability_required, status, payload,
                        parent_task_id, parent_submission_id, created_at,
                        replication_group_id, replication_slot, project_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        task_type,
                        capability_required,
                        TaskStatus.CREATED.value,
                        json.dumps(slot_payload),
                        None,
                        None,
                        created_at,
                        group_id,
                        slot,
                        project_id,
                    ),
                )
                envelope = TaskEnvelope(
                    task_id=task_id,
                    task_type=task_type,
                    capability_required=capability_required,
                    status=TaskStatus.CREATED,
                    payload=slot_payload,
                    created_at=created_at,
                    project_id=project_id,
                )
                if slot == 0:
                    first_envelope = envelope
            self._append_audit(
                conn,
                "replication.created",
                None,
                {
                    "group_id": group_id,
                    "task_type": task_type,
                    "slots": config.slots,
                    "quorum": config.quorum,
                    "parallel_kind": config.kind,
                    "good_attempt_mint": config.good_attempt_mint,
                },
            )
        assert first_envelope is not None
        return first_envelope

    def poll_tasks(self, agent_id: str, capability_filter: str | None) -> list[TaskEnvelope]:
        agent = self.get_agent(agent_id)
        if agent is None:
            return []
        capabilities = set(agent["capabilities"])
        tasks: list[TaskEnvelope] = []
        with self._conn() as conn:
            memberships = agent_project_ids(conn, agent_id)
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = ?
                ORDER BY created_at ASC
                """,
                (TaskStatus.CREATED.value,),
            ).fetchall()
            for row in rows:
                cap = row["capability_required"]
                if capability_filter and cap != capability_filter:
                    continue
                if cap not in capabilities:
                    continue
                keys = row.keys()
                task_project = (
                    row["project_id"]
                    if "project_id" in keys and row["project_id"]
                    else DEFAULT_PROJECT_ID
                )
                if task_project not in memberships:
                    continue
                task_payload = json.loads(row["payload"]) if row["payload"] else {}
                if credibility_enabled() and row["task_type"] not in (
                    "tester.run",
                    "reviewer.approve",
                ):
                    if not agent_can_claim_by_tier(
                        conn, agent_id, cap, task_project, task_payload
                    ):
                        continue
                    from agentswarm_platform.version_probation import (
                        agent_can_claim_during_probation,
                    )

                    if not agent_can_claim_during_probation(
                        conn, agent_id, task_payload
                    ):
                        continue
                group_id = row["replication_group_id"] if "replication_group_id" in keys else None
                if group_id:
                    group = conn.execute(
                        "SELECT status FROM replication_groups WHERE group_id = ?",
                        (group_id,),
                    ).fetchone()
                    if group is None or group["status"] != "pending":
                        continue
                if "assignment_only" in keys and int(row["assignment_only"] or 0) == 1:
                    continue
                tasks.append(self._row_to_task(row))
        return tasks

    def claim_task(self, task_id: str, agent_id: str, *, via_assignment: bool = False) -> ClaimResponse:
        agent = self.get_agent(agent_id)
        if agent is None:
            raise ValueError("unknown agent")
        claim_token = secrets.token_urlsafe(32)
        deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
        with self._conn() as conn:
            if is_agent_quarantined(conn, agent_id):
                raise ValueError("quarantine: agent is quarantined")
            self._assert_claim_budget(conn, agent_id)
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise ValueError("task not found")
            keys = row.keys()
            if int(row["assignment_only"] or 0) == 1 and not via_assignment:
                raise ValueError("task is assignment-only; await dispatcher assignment")
            if row["status"] != TaskStatus.CREATED.value:
                raise ValueError("task not claimable")
            if row["capability_required"] not in agent["capabilities"]:
                raise ValueError("agent lacks capability")
            group_id = row["replication_group_id"] if "replication_group_id" in keys else None
            if group_id:
                group = conn.execute(
                    "SELECT status FROM replication_groups WHERE group_id = ?",
                    (group_id,),
                ).fetchone()
                if group is None or group["status"] != "pending":
                    raise ValueError("replication group is not accepting claims")
                if agent_already_in_group(conn, group_id, agent_id):
                    raise ValueError("agent already claimed a slot in this replication group")
            task_payload = json.loads(row["payload"]) if row["payload"] else {}
            if row["task_type"] not in ("tester.run", "reviewer.approve"):
                assert_claim_tier_allowed(
                    conn,
                    agent_id=agent_id,
                    capability=row["capability_required"],
                    project_id=project_id_from_task_row(row),
                    payload=task_payload,
                )
                from agentswarm_platform.version_probation import (
                    assert_probation_allows_claim,
                )

                assert_probation_allows_claim(conn, agent_id, task_payload)
            if row["task_type"] not in ("tester.run", "reviewer.approve"):
                lock_claim_stake(
                    conn,
                    agent_id=agent_id,
                    capability=row["capability_required"],
                    task_id=task_id,
                    project_id=project_id_from_task_row(row),
                )
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, claimed_by = ?, claim_token = ?, claim_deadline = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.CLAIMED.value,
                    agent_id,
                    claim_token,
                    deadline.isoformat(),
                    task_id,
                ),
            )
            self._append_audit(
                conn,
                "task.claimed",
                agent_id,
                {"task_id": task_id, "claim_token": claim_token},
            )
        return ClaimResponse(claim_token=claim_token, deadline=deadline.isoformat())

    def checkpoint(self, claim_token: str, partial_state: dict[str, Any]) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["status"] != TaskStatus.CLAIMED.value:
                raise ValueError("task not in claimed state")
            self._append_audit(
                conn,
                "task.checkpoint",
                row["claimed_by"],
                {"task_id": row["task_id"], "partial_state": partial_state},
            )

    def submit_task(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
        *,
        enqueue_followups: bool = True,
    ) -> SubmitResponse:
        replication_status: str | None = None
        canary_passed: bool | None = None
        claiming_agent_id: str | None = None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["status"] != TaskStatus.CLAIMED.value:
                raise ValueError("task not in claimed state")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")

            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")

            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.SUBMITTED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            self._append_audit(
                conn,
                "task.submitted",
                row["claimed_by"],
                {"task_id": row["task_id"], "submission_id": submission_id},
            )

            git_artifact = result.get("git_artifact")
            if isinstance(git_artifact, dict):
                insert_git_artifact(
                    conn,
                    submission_id=submission_id,
                    task_id=row["task_id"],
                    project_id=project_id_from_task_row(row),
                    artifact=git_artifact,
                )

            task_payload = json.loads(row["payload"])
            shared_payload: dict[str, Any] | None = None
            group_id = row["replication_group_id"] if "replication_group_id" in row.keys() else None
            if group_id:
                shared_payload = json.loads(
                    conn.execute(
                        "SELECT payload FROM replication_groups WHERE group_id = ?",
                        (group_id,),
                    ).fetchone()["payload"]
                )
            canary_passed = evaluate_canary(
                conn,
                agent_id=row["claimed_by"],
                task_id=row["task_id"],
                task_type=row["task_type"],
                task_payload=task_payload,
                shared_payload=shared_payload,
                result=result,
                capability=row["capability_required"],
                project_id=project_id_from_task_row(row),
            )
            if canary_passed is not None:
                self._append_audit(
                    conn,
                    "canary.passed" if canary_passed else "canary.failed",
                    row["claimed_by"],
                    {
                        "task_id": row["task_id"],
                        "passed": canary_passed,
                    },
                )
            if group_id and shared_payload is not None:
                resolution = record_replication_submit(
                    conn,
                    group_id=group_id,
                    task_type=row["task_type"],
                    payload=shared_payload,
                    result=result,
                )
                replication_status = resolution["status"]
                self._append_audit(
                    conn,
                    f"replication.{resolution['status']}",
                    row["claimed_by"],
                    {"group_id": group_id, **resolution},
                )
            elif enqueue_followups and row["task_type"] in (
                "codewriter.patch",
                "codewriter.add-article",
            ):
                self._enqueue_verification_chain(
                    conn,
                    parent_task_id=row["task_id"],
                    parent_submission_id=submission_id,
                    result_summary=result,
                )
            claiming_agent_id = row["claimed_by"]

        if claiming_agent_id:
            self._mark_agent_idle_if_present(claiming_agent_id)
        return SubmitResponse(
            submission_id=submission_id,
            replication_status=replication_status,
            canary_passed=canary_passed,
        )

    def _enqueue_verification_chain(
        self,
        conn: sqlite3.Connection,
        parent_task_id: str,
        parent_submission_id: str,
        result_summary: dict[str, Any],
    ) -> None:
        tester_task_id = f"task_{uuid.uuid4().hex[:12]}"
        created_at = utc_now_iso()
        tester_payload = {
            "parent_submission_id": parent_submission_id,
            "parent_task_id": parent_task_id,
            "result_summary": result_summary,
        }
        project_id = self._project_id_for_task(conn, parent_task_id)
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, capability_required, status, payload,
                parent_task_id, parent_submission_id, created_at, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tester_task_id,
                "tester.run",
                "tester",
                TaskStatus.CREATED.value,
                json.dumps(tester_payload),
                parent_task_id,
                parent_submission_id,
                created_at,
                project_id,
            ),
        )
        self._append_audit(
            conn,
            "task.created",
            None,
            {
                "task_id": tester_task_id,
                "task_type": "tester.run",
                "trigger": "codewriter.submit",
            },
        )

    def _maybe_enqueue_reviewer(
        self,
        conn: sqlite3.Connection,
        tester_task_id: str,
        parent_submission_id: str,
        parent_task_id: str,
        test_result: dict[str, Any],
    ) -> None:
        if not test_result.get("passed", False):
            return
        reviewer_task_id = f"task_{uuid.uuid4().hex[:12]}"
        created_at = utc_now_iso()
        reviewer_payload = {
            "parent_submission_id": parent_submission_id,
            "parent_task_id": parent_task_id,
            "tester_task_id": tester_task_id,
            "test_result": test_result,
        }
        parent_row = conn.execute(
            "SELECT submission_result FROM tasks WHERE submission_id = ?",
            (parent_submission_id,),
        ).fetchone()
        if parent_row is not None and parent_row["submission_result"]:
            parent_result = json.loads(parent_row["submission_result"])
            git_artifact = parent_result.get("git_artifact")
            if isinstance(git_artifact, dict):
                reviewer_payload["git_artifact"] = git_artifact
        project_id = self._project_id_for_task(conn, parent_task_id)
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, capability_required, status, payload,
                parent_task_id, parent_submission_id, created_at, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reviewer_task_id,
                "reviewer.approve",
                "reviewer",
                TaskStatus.CREATED.value,
                json.dumps(reviewer_payload),
                parent_task_id,
                parent_submission_id,
                created_at,
                project_id,
            ),
        )
        self._append_audit(
            conn,
            "task.created",
            None,
            {
                "task_id": reviewer_task_id,
                "task_type": "reviewer.approve",
                "trigger": "tester.pass",
            },
        )

    def poll_verifications(self, agent_id: str) -> list[VerificationEnvelope]:
        agent = self.get_agent(agent_id)
        if agent is None or "reviewer" not in agent["capabilities"]:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT v.*, t.submission_result
                FROM verifications v
                JOIN tasks t ON t.submission_id = v.submission_id
                WHERE v.status = ? AND v.claimed_by IS NULL
                ORDER BY v.created_at ASC
                """,
                (VerificationStatus.PENDING.value,),
            ).fetchall()
        return [self._row_to_verification(row) for row in rows]

    def claim_verification(self, verification_id: str, agent_id: str) -> ClaimResponse:
        agent = self.get_agent(agent_id)
        if agent is None or "reviewer" not in agent["capabilities"]:
            raise ValueError("agent cannot verify")
        claim_token = secrets.token_urlsafe(32)
        deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
        with self._conn() as conn:
            self._assert_claim_budget(conn, agent_id)
            row = conn.execute(
                "SELECT * FROM verifications WHERE verification_id = ?",
                (verification_id,),
            ).fetchone()
            if row is None:
                raise ValueError("verification not found")
            if row["status"] != VerificationStatus.PENDING.value:
                raise ValueError("verification not pending")
            conn.execute(
                """
                UPDATE verifications
                SET claimed_by = ?, claim_token = ?, claim_deadline = ?
                WHERE verification_id = ?
                """,
                (agent_id, claim_token, deadline.isoformat(), verification_id),
            )
            self._append_audit(
                conn,
                "verification.claimed",
                agent_id,
                {"verification_id": verification_id, "claim_token": claim_token},
            )
        return ClaimResponse(claim_token=claim_token, deadline=deadline.isoformat())

    def verify_submission(
        self,
        claim_token: str,
        verdict: str,
        notes: str,
        signature: str,
    ) -> None:
        with self._conn() as conn:
            vrow = conn.execute(
                "SELECT * FROM verifications WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if vrow is not None:
                self._complete_verification_record(
                    conn, vrow, verdict, notes, signature
                )
                return

            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["status"] != TaskStatus.SUBMITTED.value:
                raise ValueError("task not awaiting verification")

            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("verifying agent missing")

            from agentswarm_platform.crypto import verify_payload

            signed_payload = {
                "task_id": row["task_id"],
                "submission_id": row["submission_id"],
                "verdict": verdict,
                "notes": notes,
            }
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid verification signature")

            new_status = (
                TaskStatus.VERIFIED.value
                if verdict == "approve"
                else TaskStatus.REJECTED.value
            )
            conn.execute(
                "UPDATE tasks SET status = ? WHERE task_id = ?",
                (new_status, row["task_id"]),
            )
            self._append_audit(
                conn,
                "task.verified",
                row["claimed_by"],
                {
                    "task_id": row["task_id"],
                    "submission_id": row["submission_id"],
                    "verdict": verdict,
                },
            )

    def _complete_verification_record(
        self,
        conn: sqlite3.Connection,
        vrow: sqlite3.Row,
        verdict: str,
        notes: str,
        signature: str,
    ) -> None:
        agent = self.get_agent(vrow["claimed_by"])
        if agent is None:
            raise ValueError("verifying agent missing")

        from agentswarm_platform.crypto import verify_payload

        signed_payload = {
            "verification_id": vrow["verification_id"],
            "submission_id": vrow["submission_id"],
            "verdict": verdict,
            "notes": notes,
        }
        if not verify_payload(agent["public_key"], signed_payload, signature):
            raise ValueError("invalid verification signature")

        status = (
            VerificationStatus.APPROVED.value
            if verdict == "approve"
            else VerificationStatus.REJECTED.value
        )
        conn.execute(
            """
            UPDATE verifications
            SET status = ?, verdict = ?, verdict_notes = ?, verdict_signature = ?
            WHERE verification_id = ?
            """,
            (status, verdict, notes, signature, vrow["verification_id"]),
        )
        parent_status = (
            TaskStatus.VERIFIED.value
            if verdict == "approve"
            else TaskStatus.REJECTED.value
        )
        conn.execute(
            "UPDATE tasks SET status = ? WHERE submission_id = ?",
            (parent_status, vrow["submission_id"]),
        )
        self._append_audit(
            conn,
            "verification.completed",
            vrow["claimed_by"],
            {
                "verification_id": vrow["verification_id"],
                "submission_id": vrow["submission_id"],
                "verdict": verdict,
            },
        )
        parent_row = conn.execute(
            "SELECT * FROM tasks WHERE submission_id = ?",
            (vrow["submission_id"],),
        ).fetchone()
        if parent_row is not None:
            apply_task_outcome(
                conn,
                parent_task_row=parent_row,
                verdict=verdict,
                reviewer_agent_id=vrow["claimed_by"],
            )

    def complete_tester_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "tester.run":
                raise ValueError("not a tester task")

            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")

            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")

            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.SUBMITTED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            self._append_audit(
                conn,
                "task.submitted",
                row["claimed_by"],
                {"task_id": row["task_id"], "submission_id": submission_id},
            )

            payload = json.loads(row["payload"])
            self._maybe_enqueue_reviewer(
                conn,
                tester_task_id=row["task_id"],
                parent_submission_id=payload["parent_submission_id"],
                parent_task_id=payload["parent_task_id"],
                test_result=result,
            )

        return SubmitResponse(submission_id=submission_id)

    def complete_reviewer_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "reviewer.approve":
                raise ValueError("not a reviewer task")

            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")

            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")

            verdict = "approve" if result.get("approved", False) else "reject"
            submission_id = row["submission_id"] or f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            new_status = (
                TaskStatus.VERIFIED.value
                if verdict == "approve"
                else TaskStatus.REJECTED.value
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    new_status,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )

            payload = json.loads(row["payload"])
            parent_submission_id = payload["parent_submission_id"]
            conn.execute(
                "UPDATE tasks SET status = ? WHERE submission_id = ?",
                (new_status, parent_submission_id),
            )

            self._append_audit(
                conn,
                "task.verified",
                row["claimed_by"],
                {
                    "task_id": row["task_id"],
                    "parent_submission_id": parent_submission_id,
                    "verdict": verdict,
                },
            )
            parent_row = conn.execute(
                "SELECT * FROM tasks WHERE submission_id = ?",
                (parent_submission_id,),
            ).fetchone()
            if parent_row is not None:
                apply_task_outcome(
                    conn,
                    parent_task_row=parent_row,
                    verdict=verdict,
                    reviewer_agent_id=row["claimed_by"],
                )

        return SubmitResponse(submission_id=submission_id)

    def complete_planner_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "planner.plan":
                raise ValueError("not a planner task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            enqueue_specs = result.get("enqueue")
            if not isinstance(enqueue_specs, list) or not enqueue_specs:
                raise ValueError("planner result requires non-empty enqueue list")
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            enqueued = enqueue_child_tasks(
                conn,
                parent_task_id=row["task_id"],
                specs=enqueue_specs,
                trigger="planner.plan",
                append_audit=self._append_audit,
                project_id=self._project_id_for_task(conn, row["task_id"]),
            )
            self._append_audit(
                conn,
                "planner.completed",
                row["claimed_by"],
                {
                    "task_id": row["task_id"],
                    "goal": result.get("goal"),
                    "enqueued_task_ids": enqueued,
                },
            )
        return SubmitResponse(
            submission_id=submission_id,
            enqueued_task_ids=enqueued,
        )

    def complete_orchestrator_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "orchestrator.scan":
                raise ValueError("not an orchestrator task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            enqueue_specs = result.get("enqueue", [])
            if enqueue_specs and not isinstance(enqueue_specs, list):
                raise ValueError("orchestrator enqueue must be a list")
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            enqueued: list[str] = []
            if enqueue_specs:
                enqueued = enqueue_child_tasks(
                    conn,
                    parent_task_id=row["task_id"],
                    specs=enqueue_specs,
                    trigger="orchestrator.scan",
                    append_audit=self._append_audit,
                    project_id=self._project_id_for_task(conn, row["task_id"]),
                )
            self._append_audit(
                conn,
                "orchestrator.completed",
                row["claimed_by"],
                {
                    "task_id": row["task_id"],
                    "gaps": result.get("gaps", []),
                    "enqueued_task_ids": enqueued,
                },
            )
        return SubmitResponse(
            submission_id=submission_id,
            enqueued_task_ids=enqueued or None,
        )

    def complete_moderator_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "moderator.scan":
                raise ValueError("not a moderator task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            actions = result.get("actions", [])
            if actions and not isinstance(actions, list):
                raise ValueError("moderator actions must be a list")
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            applied: list[dict[str, Any]] = []
            for action in actions:
                applied.append(apply_moderator_action(conn, action))
            self._append_audit(
                conn,
                "moderator.completed",
                row["claimed_by"],
                {
                    "task_id": row["task_id"],
                    "findings": result.get("findings", []),
                    "applied_actions": applied,
                },
            )
        return SubmitResponse(submission_id=submission_id)

    def get_task_payload_by_claim_token(self, claim_token: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["payload"]) if row["payload"] else {}

    def complete_scraper_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        from agentswarm_platform.content_pipeline import (
            summarizer_enqueue_spec,
            validate_scraper_result,
        )

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "scraper.fetch":
                raise ValueError("not a scraper task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            drafts = validate_scraper_result(result)
            enqueue_specs = [summarizer_enqueue_spec(draft) for draft in drafts]
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            enqueued = enqueue_child_tasks(
                conn,
                parent_task_id=row["task_id"],
                specs=enqueue_specs,
                trigger="scraper.fetch",
                append_audit=self._append_audit,
                project_id=self._project_id_for_task(conn, row["task_id"]),
            )
            self._append_audit(
                conn,
                "scraper.completed",
                row["claimed_by"],
                {
                    "task_id": row["task_id"],
                    "draft_count": len(drafts),
                    "enqueued_task_ids": enqueued,
                },
            )
        return SubmitResponse(submission_id=submission_id, enqueued_task_ids=enqueued)

    def complete_summarizer_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        from agentswarm_platform.content_pipeline import (
            classifier_enqueue_spec,
            validate_summarizer_result,
        )

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "summarizer.summarize":
                raise ValueError("not a summarizer task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            draft, summary = validate_summarizer_result(result)
            enqueue_specs = [classifier_enqueue_spec(draft=draft, summary=summary)]
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            enqueued = enqueue_child_tasks(
                conn,
                parent_task_id=row["task_id"],
                specs=enqueue_specs,
                trigger="summarizer.summarize",
                append_audit=self._append_audit,
                project_id=self._project_id_for_task(conn, row["task_id"]),
            )
            self._append_audit(
                conn,
                "summarizer.completed",
                row["claimed_by"],
                {"task_id": row["task_id"], "enqueued_task_ids": enqueued},
            )
        return SubmitResponse(submission_id=submission_id, enqueued_task_ids=enqueued)

    def complete_classifier_pipeline_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        from agentswarm_platform.content_pipeline import (
            build_article,
            codewriter_enqueue_spec,
            validate_classifier_result,
        )

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "classifier.label":
                raise ValueError("not a classifier task")
            payload = json.loads(row["payload"]) if row["payload"] else {}
            if not payload.get("pipeline"):
                raise ValueError("not a pipeline classifier task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            label = validate_classifier_result(result, payload)
            draft = payload.get("draft")
            summary = payload.get("summary")
            if not isinstance(draft, dict) or not isinstance(summary, str):
                raise ValueError("pipeline classifier payload incomplete")
            article = build_article(draft=draft, summary=summary, label=label)
            enqueue_specs = [codewriter_enqueue_spec(article)]
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            enqueued = enqueue_child_tasks(
                conn,
                parent_task_id=row["task_id"],
                specs=enqueue_specs,
                trigger="classifier.label",
                append_audit=self._append_audit,
                project_id=self._project_id_for_task(conn, row["task_id"]),
            )
            self._append_audit(
                conn,
                "classifier.pipeline.completed",
                row["claimed_by"],
                {
                    "task_id": row["task_id"],
                    "article_id": article["id"],
                    "enqueued_task_ids": enqueued,
                },
            )
        return SubmitResponse(submission_id=submission_id, enqueued_task_ids=enqueued)

    def complete_deploy_approve_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "deploy.approve":
                raise ValueError("not a deploy approve task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            decision = str(result.get("decision", "approve"))
            task_payload = json.loads(row["payload"]) if row["payload"] else {}
            request_id = str(task_payload.get("request_id", ""))
            if not request_id:
                raise ValueError("deploy task missing request_id")
            if decision == "reject":
                reject_deploy_request(
                    conn,
                    request_id=request_id,
                    reason=str(result.get("reason", "rejected by reviewer")),
                )
                submission_id = f"sub_{uuid.uuid4().hex[:12]}"
                submitted_at = utc_now_iso()
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, submitted_at = ?, submission_id = ?,
                        submission_result = ?, submission_signature = ?
                    WHERE task_id = ?
                    """,
                    (
                        TaskStatus.VERIFIED.value,
                        submitted_at,
                        submission_id,
                        json.dumps(result),
                        signature,
                        row["task_id"],
                    ),
                )
                self._append_audit(
                    conn,
                    "deploy.rejected",
                    row["claimed_by"],
                    {"request_id": request_id, "task_id": row["task_id"]},
                )
                return SubmitResponse(submission_id=submission_id)
            if decision != "approve":
                raise ValueError("deploy approve decision must be approve or reject")
            project_id = project_id_from_task_row(row)
            project = get_project(conn, project_id)
            if project is None:
                raise ValueError(f"unknown project: {project_id}")
            policy = resolve_deploy_policy(project.get("governance_config"))
            capability, score = assert_deploy_signoff_allowed(
                conn,
                agent=agent,
                agent_id=row["claimed_by"],
                project_id=project_id,
                policy=policy,
            )
            record_deploy_signoff(
                conn,
                request_id=request_id,
                agent_id=row["claimed_by"],
                capability=capability,
                score=score,
                task_id=row["task_id"],
            )
            status = refresh_deploy_request_status(
                conn,
                request_id,
                append_audit=self._append_audit,
                actor_id=row["claimed_by"],
            )
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            self._append_audit(
                conn,
                "deploy.signoff",
                row["claimed_by"],
                {
                    "request_id": request_id,
                    "task_id": row["task_id"],
                    "capability": capability,
                    "score": score,
                    "request_status": status,
                },
            )
        return SubmitResponse(submission_id=submission_id)

    def complete_deploy_execute_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "deploy.execute":
                raise ValueError("not a deploy execute task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            if "deployer" not in agent.get("capabilities", []):
                raise ValueError("agent lacks deployer capability")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            task_payload = json.loads(row["payload"]) if row["payload"] else {}
            request_id = str(task_payload.get("request_id", ""))
            if not request_id:
                raise ValueError("deploy task missing request_id")
            record_deploy_execution(
                conn,
                request_id=request_id,
                agent_id=row["claimed_by"],
                result=result,
            )
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            self._append_audit(
                conn,
                "deploy.executed",
                row["claimed_by"],
                {
                    "request_id": request_id,
                    "task_id": row["task_id"],
                    "outcome": result.get("outcome"),
                },
            )
        return SubmitResponse(submission_id=submission_id)

    def list_moderation_flags(
        self, *, status: str | None = "open", limit: int = 50
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return list_moderation_flags(conn, status=status, limit=limit)

    def list_memory(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return list_memory_entries(conn)

    def get_memory(self, memory_key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return get_memory_entry(conn, memory_key)

    def upsert_memory(
        self,
        *,
        memory_key: str,
        content: dict[str, Any],
        tags: list[str] | None,
        updated_by: str | None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            return upsert_memory_entry(
                conn,
                memory_key=memory_key,
                content=content,
                tags=tags,
                updated_by=updated_by,
            )

    def upsert_memory_by_agent(
        self,
        *,
        memory_key: str,
        content: dict[str, Any],
        tags: list[str] | None,
        agent_id: str,
        signature: str,
    ) -> dict[str, Any]:
        from agentswarm_platform.crypto import verify_payload

        with self._conn() as conn:
            agent = self.get_agent(agent_id)
            if agent is None:
                raise ValueError("unknown agent")
            signed_payload = {
                "memory_key": memory_key,
                "content": content,
                "tags": tags or [],
                "agent_id": agent_id,
            }
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid memory write signature")
            project_id = assert_agent_memory_write_allowed(
                conn,
                agent=agent,
                agent_id=agent_id,
                memory_key=memory_key,
            )
            entry = upsert_memory_entry(
                conn,
                memory_key=memory_key,
                content=content,
                tags=tags,
                updated_by=agent_id,
            )
            self._append_audit(
                conn,
                "memory.updated",
                agent_id,
                {
                    "memory_key": memory_key,
                    "project_id": project_id,
                    "via": "agent",
                },
            )
            return entry

    def get_platform_summary(self) -> dict[str, Any]:
        with self._conn() as conn:
            task_rows = conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM tasks
                GROUP BY status
                """
            ).fetchall()
            repl_rows = conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM replication_groups
                GROUP BY status
                """
            ).fetchall()
            canary_rows = conn.execute(
                """
                SELECT agent_id,
                       SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) AS failures,
                       COUNT(*) AS attempts
                FROM canary_events
                GROUP BY agent_id
                HAVING failures > 0
                ORDER BY failures DESC
                LIMIT 5
                """
            ).fetchall()
            memory_rows = conn.execute(
                "SELECT memory_key FROM memory_entries ORDER BY memory_key ASC"
            ).fetchall()
            deploy_summary = summarize_deploy_requests(conn)
            owner_clusters = summarize_owner_clusters(conn, min_agents=3)
        tasks = {row["status"]: int(row["n"]) for row in task_rows}
        replication_groups = {row["status"]: int(row["n"]) for row in repl_rows}
        canary_failures_top = [
            {
                "agent_id": row["agent_id"],
                "failures": int(row["failures"]),
                "attempts": int(row["attempts"]),
            }
            for row in canary_rows
        ]
        return {
            "tasks": tasks,
            "replication_groups": replication_groups,
            "canary_failures_top": canary_failures_top,
            "memory_keys": [row["memory_key"] for row in memory_rows],
            "deploy_requests": deploy_summary,
            "owner_clusters": owner_clusters,
        }

    def get_agent_credibility(
        self, agent_id: str, project_id: str = DEFAULT_PROJECT_ID
    ) -> list[dict[str, Any]] | None:
        if self.get_agent(agent_id) is None:
            return None
        with self._conn() as conn:
            return list_agent_credibility(conn, agent_id, project_id)

    def get_agent_profile(
        self, agent_id: str, project_id: str = DEFAULT_PROJECT_ID
    ) -> dict[str, Any] | None:
        from agentswarm_platform.credibility_gamification import build_agent_profile

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if row is None:
                return None
            keys = row.keys()
            agent = {
                "agent_id": row["agent_id"],
                "owner": row["owner"],
                "capabilities": json.loads(row["capabilities"]),
                "quarantined": bool(row["quarantined"]) if "quarantined" in keys else False,
            }
            credibility_rows = list_agent_credibility(conn, agent_id, project_id)
            from agentswarm_platform.version_probation import probation_status

            profile = build_agent_profile(
                conn,
                agent,
                project_id=project_id,
                credibility_rows=credibility_rows,
            )
            profile["version_probation"] = probation_status(conn, agent_id)
            return profile

    def get_replication_group_status(self, group_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return get_replication_group(conn, group_id)

    def get_agent_canary_stats(self, agent_id: str) -> dict[str, Any] | None:
        if self.get_agent(agent_id) is None:
            return None
        with self._conn() as conn:
            return get_canary_stats(conn, agent_id)

    def get_credibility_leaderboard(
        self,
        capability: str | None,
        limit: int,
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return credibility_leaderboard(conn, capability, limit, project_id)

    def apply_credibility_decay(
        self, *, project_id: str | None = None
    ) -> dict[str, int]:
        with self._conn() as conn:
            return apply_inactivity_decay_all(conn, project_id=project_id)

    def get_owner_anchoring(self, owner_id: str) -> dict[str, float | str] | None:
        with self._conn() as conn:
            return owner_anchoring_summary(conn, owner_id)

    def create_deploy_request(
        self,
        *,
        project_id: str,
        environment: str,
        artifact_ref: str,
        description: str | None,
        owner_id: str,
        required_signoffs: int | None = None,
        min_credibility: float | None = None,
    ) -> dict[str, Any]:
        resolved_project = validate_project_id(project_id)
        env = environment.strip()
        artifact = artifact_ref.strip()
        if not env:
            raise ValueError("environment is required")
        if not artifact:
            raise ValueError("artifact_ref is required")
        with self._conn() as conn:
            project = get_project(conn, resolved_project)
            if project is None:
                raise ValueError(f"unknown project: {resolved_project}")
            base_policy = resolve_deploy_policy_for_environment(
                project.get("governance_config"),
                env,
            )
            policy = DeployPolicy(
                required_signoffs=(
                    required_signoffs
                    if required_signoffs is not None
                    else base_policy.required_signoffs
                ),
                min_credibility=(
                    min_credibility
                    if min_credibility is not None
                    else base_policy.min_credibility
                ),
                signoff_capabilities=base_policy.signoff_capabilities,
            )
            request = insert_deploy_request(
                conn,
                project_id=resolved_project,
                environment=env,
                artifact_ref=artifact,
                description=description,
                owner_id=owner_id,
                policy=policy,
            )
            task_ids = enqueue_deploy_approve_tasks(
                conn,
                request_id=request["request_id"],
                project_id=resolved_project,
                policy=policy,
                append_audit=self._append_audit,
                actor_id=owner_id,
            )
            self._append_audit(
                conn,
                "deploy.requested",
                owner_id,
                {
                    "request_id": request["request_id"],
                    "project_id": resolved_project,
                    "environment": env,
                    "artifact_ref": artifact,
                    "task_ids": task_ids,
                },
            )
            request["approve_task_ids"] = task_ids
            return request

    def list_deploy_requests(
        self,
        *,
        status: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return list_deploy_request_rows(
                conn, status=status, project_id=project_id, limit=limit
            )

    def get_deploy_request(self, request_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return get_deploy_request_row(conn, request_id)

    def import_agent_credibility(
        self,
        agent_id: str,
        source_project_id: str,
        target_project_id: str,
        capabilities: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.get_agent(agent_id) is None:
            raise ValueError("unknown agent")
        with self._conn() as conn:
            return import_cross_project_credibility(
                conn,
                agent_id=agent_id,
                source_project_id=source_project_id,
                target_project_id=target_project_id,
                capabilities=capabilities,
            )

    def get_task_type_by_claim_token(self, claim_token: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT task_type FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
        return row["task_type"] if row else None

    def get_task(self, task_id: str) -> TaskEnvelope | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_audit_events(self, limit: int = 50) -> list[AuditEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        events: list[AuditEvent] = []
        for row in reversed(rows):
            events.append(
                AuditEvent(
                    seq=row["seq"],
                    timestamp=row["timestamp"],
                    event_type=row["event_type"],
                    actor_id=row["actor_id"],
                    details=json.loads(row["details"]),
                    prev_hash=row["prev_hash"],
                    entry_hash=row["entry_hash"],
                )
            )
        return events

    def _row_to_task(self, row: sqlite3.Row) -> TaskEnvelope:
        keys = row.keys()
        project_id = (
            row["project_id"]
            if "project_id" in keys and row["project_id"]
            else DEFAULT_PROJECT_ID
        )
        return TaskEnvelope(
            task_id=row["task_id"],
            task_type=row["task_type"],
            capability_required=row["capability_required"],
            status=TaskStatus(row["status"]),
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
            parent_task_id=row["parent_task_id"],
            project_id=project_id,
        )

    def _project_id_for_task(
        self, conn: sqlite3.Connection, task_id: str | None
    ) -> str:
        if not task_id:
            return DEFAULT_PROJECT_ID
        row = conn.execute(
            "SELECT project_id FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return DEFAULT_PROJECT_ID
        keys = row.keys()
        if "project_id" not in keys or not row["project_id"]:
            return DEFAULT_PROJECT_ID
        return row["project_id"]

    def _row_to_verification(self, row: sqlite3.Row) -> VerificationEnvelope:
        return VerificationEnvelope(
            verification_id=row["verification_id"],
            submission_id=row["submission_id"],
            task_id=row["task_id"],
            task_type=row["task_type"],
            status=VerificationStatus(row["status"]),
            result_summary=json.loads(row["result_summary"]),
        )

    def record_agent_presence(
        self,
        agent_id: str,
        *,
        status: str,
        capabilities: list[str],
        model_id: str | None,
        load: float,
        client_version: str | None,
        ttl_sec: int,
    ) -> dict[str, Any]:
        agent = self.get_agent(agent_id)
        if agent is None:
            raise ValueError("unknown agent")
        if status not in ("idle", "busy"):
            raise ValueError("status must be idle or busy")
        with self._conn() as conn:
            recorded = upsert_presence(
                conn,
                agent_id=agent_id,
                status=status,
                capabilities=capabilities,
                model_id=model_id,
                load=load,
                client_version=client_version,
                ttl_sec=ttl_sec,
            )
            self._append_audit(
                conn,
                "agent.presence",
                agent_id,
                {"status": status, "capabilities": capabilities, "model_id": model_id},
            )
        return recorded

    def request_pool_need(
        self,
        *,
        role: str,
        capability_required: str,
        parent_task_id: str | None,
        task_id: str | None,
        project_id: str,
        task_type: str | None,
        payload: dict[str, Any],
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        if not dispatch_enabled():
            raise ValueError("pool.need requires AGENTSWARM_ASSIGNMENT_MODE=dispatch")
        resolved_project = validate_project_id(project_id)
        resolved_task_id = task_id
        if resolved_task_id is None:
            resolved_type = task_type or f"{role}.assigned"
            created = self.create_task(
                resolved_type,
                capability_required,
                payload,
                parent_task_id=parent_task_id,
                project_id=resolved_project,
                assignment_only=True,
            )
            resolved_task_id = created.task_id
        with self._conn() as conn:
            row = conn.execute(
                "SELECT task_id, assignment_only FROM tasks WHERE task_id = ?",
                (resolved_task_id,),
            ).fetchone()
            if row is None:
                raise ValueError("task not found")
            if int(row["assignment_only"] or 0) != 1:
                raise ValueError("pool.need tasks must be assignment_only")
            need_id = insert_pool_need(
                conn,
                role=role,
                capability_required=capability_required,
                task_id=resolved_task_id,
                project_id=resolved_project,
                parent_task_id=parent_task_id,
                constraints=constraints,
            )
            self._append_audit(
                conn,
                "pool.need",
                None,
                {
                    "need_id": need_id,
                    "role": role,
                    "task_id": resolved_task_id,
                    "constraints": constraints,
                },
            )
        assignment = self._dispatch_need(need_id)
        return {
            "need_id": need_id,
            "task_id": resolved_task_id,
            "assigned": assignment is not None,
            "assignment": assignment,
        }

    def _dispatch_need(self, need_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            need_row = get_pool_need(conn, need_id)
            if need_row is None or need_row["status"] != "pending":
                return None
            agent_id = pick_dispatch_agent(conn, need_row)
            if agent_id is None:
                return None
            claim_token = new_claim_token()
            deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
            task_id = need_row["task_id"]
            agent = self.get_agent(agent_id)
            if agent is None:
                return None
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None or row["status"] != TaskStatus.CREATED.value:
                return None
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, claimed_by = ?, claim_token = ?, claim_deadline = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.CLAIMED.value,
                    agent_id,
                    claim_token,
                    deadline.isoformat(),
                    task_id,
                ),
            )
            lease = create_assignment_lease(
                conn,
                need_id=need_id,
                agent_id=agent_id,
                task_id=task_id,
                claim_token=claim_token,
            )
            mark_need_assigned(conn, need_id=need_id, agent_id=agent_id, lease_id=lease["lease_id"])
            set_presence_status(conn, agent_id, "busy")
            self._append_audit(
                conn,
                "pool.assign",
                agent_id,
                {"need_id": need_id, "task_id": task_id, "lease_id": lease["lease_id"]},
            )
        assignment = self.get_pending_assignment(agent_id)
        return assignment

    def get_pending_assignment(self, agent_id: str) -> dict[str, Any] | None:
        agent = self.get_agent(agent_id)
        if agent is None:
            return None
        with self._conn() as conn:
            return get_pending_assignment_for_agent(conn, agent_id)

    def _mark_agent_idle_if_present(self, agent_id: str) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT agent_id FROM agent_presence WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if row is not None:
                set_presence_status(conn, agent_id, "idle")

    def get_agent_credits(self, agent_id: str) -> dict[str, Any] | None:
        agent = self.get_agent(agent_id)
        if agent is None:
            return None
        with self._conn() as conn:
            balance = get_credits_balance(conn, agent_id)
        return {
            "agent_id": agent_id,
            "balance": balance,
            "enabled": credits_enabled(),
        }

    def create_creative_goal(
        self,
        *,
        poster_agent_id: str,
        brief: str,
        rubric: list[dict[str, Any]],
        project_id: str | None = None,
        min_reviewers: int = 3,
        pass_threshold: float = 6.0,
        difficulty: float = 1.0,
    ) -> dict[str, Any]:
        if not dispatch_enabled():
            raise ValueError("creative goals require AGENTSWARM_ASSIGNMENT_MODE=dispatch")
        if min_reviewers < 1:
            raise ValueError("min_reviewers must be at least 1")
        if not rubric:
            raise ValueError("rubric must not be empty")
        poster = self.get_agent(poster_agent_id)
        if poster is None:
            raise ValueError("poster agent not found")
        resolved_project = validate_project_id(project_id or DEFAULT_PROJECT_ID)
        with self._conn() as conn:
            goal_id = insert_creative_goal(
                conn,
                poster_agent_id=poster_agent_id,
                project_id=resolved_project,
                brief=brief,
                rubric=rubric,
                min_reviewers=min_reviewers,
                pass_threshold=pass_threshold,
            )
            if credits_enabled():
                cost = post_cost("creative.goal", difficulty=difficulty)
                burn_credits(
                    conn,
                    poster_agent_id,
                    cost,
                    reason="goal_post",
                    ref_type="creative_goal",
                    ref_id=goal_id,
                )
        coordinator_payload = {
            "goal_id": goal_id,
            "capsule": {
                "goal_id": goal_id,
                "brief": brief,
                "rubric": rubric,
                "min_reviewers": min_reviewers,
            },
        }
        coordinator_task = self.create_task(
            "coordinator.decompose",
            "coordinator",
            coordinator_payload,
            project_id=resolved_project,
            assignment_only=True,
        )
        self.request_pool_need(
            role="coordinator",
            capability_required="coordinator",
            parent_task_id=coordinator_task.task_id,
            task_id=coordinator_task.task_id,
            project_id=resolved_project,
            task_type="coordinator.decompose",
            payload=coordinator_payload,
            constraints={},
        )
        return {
            "goal_id": goal_id,
            "coordinator_task_id": coordinator_task.task_id,
            "status": "pending",
        }

    def get_creative_goal_status(self, goal_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            goal = get_creative_goal(conn, goal_id)
            if goal is None:
                return None
            reviews = list_reviews_for_goal(conn, goal_id)
        goal["reviews"] = reviews
        return goal

    def _emit_pool_need_spec(
        self,
        *,
        spec: dict[str, Any],
        parent_task_id: str,
        project_id: str,
        goal: dict[str, Any],
        poster_owner: str,
        worker_agent_id: str | None = None,
        payload_override: dict[str, Any] | None = None,
    ) -> str:
        payload = payload_override if payload_override is not None else spec["payload"]
        constraints = resolve_pool_need_constraints(
            spec.get("constraints"),
            goal=goal,
            poster_owner=poster_owner,
            worker_agent_id=worker_agent_id,
        )
        created = self.create_task(
            spec["task_type"],
            spec["capability_required"],
            payload,
            parent_task_id=parent_task_id,
            project_id=project_id,
            assignment_only=True,
        )
        self.request_pool_need(
            role=spec["role"],
            capability_required=spec["capability_required"],
            parent_task_id=parent_task_id,
            task_id=created.task_id,
            project_id=project_id,
            task_type=spec["task_type"],
            payload=payload,
            constraints=constraints,
        )
        return created.task_id

    def _execute_coordinator_plan(
        self,
        *,
        plan: dict[str, Any],
        coordinator_task_id: str,
    ) -> list[str]:
        goal_id = plan["goal_id"]
        with self._conn() as conn:
            goal = get_creative_goal(conn, goal_id)
        if goal is None:
            raise ValueError("goal not found")
        poster = self.get_agent(goal["poster_agent_id"])
        if poster is None:
            raise ValueError("poster agent missing")
        enqueued: list[str] = []
        for need in plan["pool_needs"]:
            task_id = self._emit_pool_need_spec(
                spec=need,
                parent_task_id=coordinator_task_id,
                project_id=goal["project_id"],
                goal=goal,
                poster_owner=poster["owner"],
            )
            enqueued.append(task_id)
        deferred = plan.get("deferred_pool_needs") or []
        if deferred:
            with self._conn() as conn:
                set_goal_deferred_pool_needs(conn, goal_id, deferred)
        return enqueued

    def _execute_deferred_pool_needs_for_goal(
        self,
        *,
        goal_id: str,
        after_task_type: str,
        parent_task_id: str,
        worker_agent_id: str | None,
    ) -> list[str]:
        with self._conn() as conn:
            goal = get_creative_goal(conn, goal_id)
        if goal is None:
            raise ValueError("goal not found")
        deferred_entries = goal.get("deferred_pool_needs") or []
        if not deferred_entries:
            return []
        poster = self.get_agent(goal["poster_agent_id"])
        if poster is None:
            raise ValueError("poster agent missing")
        enqueued: list[str] = []
        remaining: list[dict[str, Any]] = []
        for entry in deferred_entries:
            if entry.get("after_task_type") != after_task_type:
                remaining.append(entry)
                continue
            spec = entry["spec"]
            count = int(spec.get("count", 1))
            payload_template = spec["payload_template"]
            for _ in range(count):
                payload = materialize_deferred_payload(payload_template, goal=goal)
                task_id = self._emit_pool_need_spec(
                    spec={
                        "role": spec["role"],
                        "capability_required": spec["capability_required"],
                        "task_type": spec["task_type"],
                        "constraints": spec.get("constraints"),
                    },
                    parent_task_id=parent_task_id,
                    project_id=goal["project_id"],
                    goal=goal,
                    poster_owner=poster["owner"],
                    worker_agent_id=worker_agent_id,
                    payload_override=payload,
                )
                enqueued.append(task_id)
        with self._conn() as conn:
            if remaining:
                set_goal_deferred_pool_needs(conn, goal_id, remaining)
            else:
                clear_goal_deferred_pool_needs(conn, goal_id)
        return enqueued

    def _maybe_finalize_subjective_quorum(self, conn: sqlite3.Connection, goal_id: str) -> None:
        goal = get_creative_goal(conn, goal_id)
        if goal is None or goal["status"] in ("verified", "rejected"):
            return
        reviews = list_reviews_for_goal(conn, goal_id)
        if len(reviews) < goal["min_reviewers"]:
            return
        passed, aggregate = aggregate_quorum(
            reviews,
            goal["rubric"],
            pass_threshold=goal["pass_threshold"],
        )
        status = "verified" if passed else "rejected"
        resolve_goal(conn, goal_id, status=status, aggregate_score=aggregate)
        if credits_enabled() and passed:
            reward = reviewer_reward_for("reviewer.subjective")
            for review in reviews:
                mint_credits(
                    conn,
                    review["reviewer_agent_id"],
                    reward,
                    reason="subjective_review",
                    ref_type="creative_goal",
                    ref_id=goal_id,
                    details={"aggregate_score": aggregate},
                )
        self._append_audit(
            conn,
            f"creative_goal.{status}",
            None,
            {
                "goal_id": goal_id,
                "aggregate_score": aggregate,
                "review_count": len(reviews),
            },
        )

    def complete_coordinator_decompose_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "coordinator.decompose":
                raise ValueError("not a coordinator task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            payload = json.loads(row["payload"])
            goal_id = payload.get("goal_id")
            if not goal_id:
                raise ValueError("coordinator task missing goal_id")
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            self._append_audit(
                conn,
                "coordinator.completed",
                row["claimed_by"],
                {"task_id": row["task_id"], "goal_id": goal_id},
            )
            claiming_agent_id = row["claimed_by"]
        self._mark_agent_idle_if_present(claiming_agent_id)
        with self._conn() as conn:
            goal = get_creative_goal(conn, goal_id)
        if goal is None:
            raise ValueError("goal not found")
        if "pool_needs" not in result:
            result = build_default_creative_goal_plan(goal)
        plan = validate_coordinator_plan(result, goal_id=goal_id)
        enqueued = self._execute_coordinator_plan(
            plan=plan,
            coordinator_task_id=row["task_id"],
        )
        return SubmitResponse(
            submission_id=submission_id,
            enqueued_task_ids=enqueued,
        )

    def complete_creative_text_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "creative.text":
                raise ValueError("not a creative.text task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            payload = json.loads(row["payload"])
            goal_id = payload.get("goal_id")
            if not goal_id:
                raise ValueError("creative task missing goal_id")
            text = result.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("creative.text result requires non-empty text")
            set_goal_artifact(conn, goal_id, text.strip())
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            self._append_audit(
                conn,
                "creative.text.completed",
                row["claimed_by"],
                {"task_id": row["task_id"], "goal_id": goal_id},
            )
            parent_task_id = row["task_id"]
            claiming_agent_id = row["claimed_by"]
        self._mark_agent_idle_if_present(claiming_agent_id)
        reviewer_task_ids = self._execute_deferred_pool_needs_for_goal(
            goal_id=goal_id,
            after_task_type="creative.text",
            parent_task_id=parent_task_id,
            worker_agent_id=claiming_agent_id,
        )
        return SubmitResponse(
            submission_id=submission_id,
            enqueued_task_ids=reviewer_task_ids,
        )

    def complete_reviewer_subjective_submit(
        self,
        claim_token: str,
        result: dict[str, Any],
        signature: str,
    ) -> SubmitResponse:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE claim_token = ?", (claim_token,)
            ).fetchone()
            if row is None:
                raise ValueError("invalid claim token")
            if row["task_type"] != "reviewer.subjective":
                raise ValueError("not a reviewer.subjective task")
            agent = self.get_agent(row["claimed_by"])
            if agent is None:
                raise ValueError("claiming agent missing")
            from agentswarm_platform.crypto import verify_payload

            signed_payload = {"task_id": row["task_id"], "result": result}
            if not verify_payload(agent["public_key"], signed_payload, signature):
                raise ValueError("invalid submission signature")
            payload = json.loads(row["payload"])
            goal_id = payload.get("goal_id")
            if not goal_id:
                raise ValueError("reviewer task missing goal_id")
            goal = get_creative_goal(conn, goal_id)
            if goal is None:
                raise ValueError("goal not found")
            scores = result.get("scores")
            if not isinstance(scores, dict):
                raise ValueError("reviewer result requires scores object")
            rationale = result.get("rationale", "")
            if not isinstance(rationale, str):
                raise ValueError("reviewer rationale must be a string")
            weighted_review_score(scores, goal["rubric"])
            insert_subjective_review(
                conn,
                goal_id=goal_id,
                reviewer_agent_id=row["claimed_by"],
                task_id=row["task_id"],
                scores={k: float(v) for k, v in scores.items()},
                rationale=rationale,
            )
            submission_id = f"sub_{uuid.uuid4().hex[:12]}"
            submitted_at = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, submission_id = ?,
                    submission_result = ?, submission_signature = ?
                WHERE task_id = ?
                """,
                (
                    TaskStatus.VERIFIED.value,
                    submitted_at,
                    submission_id,
                    json.dumps(result),
                    signature,
                    row["task_id"],
                ),
            )
            self._append_audit(
                conn,
                "reviewer.subjective.completed",
                row["claimed_by"],
                {"task_id": row["task_id"], "goal_id": goal_id},
            )
            self._maybe_finalize_subjective_quorum(conn, goal_id)
            claiming_agent_id = row["claimed_by"]
        self._mark_agent_idle_if_present(claiming_agent_id)
        return SubmitResponse(submission_id=submission_id)
