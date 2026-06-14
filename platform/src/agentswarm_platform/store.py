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
    apply_task_outcome,
    ensure_credibility_schema,
    leaderboard as credibility_leaderboard,
    list_agent_credibility,
    lock_claim_stake,
    seed_agent_capabilities,
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
        ensure_credibility_schema(conn)
        ensure_replication_schema(conn)

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
    ) -> AgentRegisterResponse:
        credential = secrets.token_urlsafe(24)
        budget_json = json.dumps(resource_budget) if resource_budget is not None else None
        egress_json = json.dumps(egress_allowlist) if egress_allowlist is not None else None
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT agent_id FROM agents WHERE public_key = ?", (public_key,)
            ).fetchone()
            if existing is not None:
                agent_id = existing["agent_id"]
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
                self._append_audit(
                    conn,
                    "agent.reconnected",
                    agent_id,
                    {
                        "owner": owner,
                        "owner_id": owner_id,
                        "capabilities": capabilities,
                    },
                )
                seed_agent_capabilities(conn, agent_id, capabilities)
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
            self._append_audit(
                conn,
                "agent.registered",
                agent_id,
                {
                    "owner": owner,
                    "owner_id": owner_id,
                    "capabilities": capabilities,
                },
            )
            seed_agent_capabilities(conn, agent_id, capabilities)
        return AgentRegisterResponse(agent_id=agent_id, credential=credential)

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
    ) -> TaskEnvelope:
        replication = parse_replication_config(task_type, payload)
        if replication is not None:
            return self._create_replication_tasks(
                task_type=task_type,
                capability_required=capability_required,
                payload=payload,
                config=replication,
            )
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        created_at = utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, task_type, capability_required, status, payload,
                    parent_task_id, parent_submission_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        )

    def _create_replication_tasks(
        self,
        *,
        task_type: str,
        capability_required: str,
        payload: dict[str, Any],
        config: ReplicationConfig,
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
                    slots, quorum, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                        replication_group_id, replication_slot
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
                envelope = TaskEnvelope(
                    task_id=task_id,
                    task_type=task_type,
                    capability_required=capability_required,
                    status=TaskStatus.CREATED,
                    payload=slot_payload,
                    created_at=created_at,
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
                group_id = row["replication_group_id"] if "replication_group_id" in keys else None
                if group_id:
                    group = conn.execute(
                        "SELECT status FROM replication_groups WHERE group_id = ?",
                        (group_id,),
                    ).fetchone()
                    if group is None or group["status"] != "pending":
                        continue
                tasks.append(self._row_to_task(row))
        return tasks

    def claim_task(self, task_id: str, agent_id: str) -> ClaimResponse:
        agent = self.get_agent(agent_id)
        if agent is None:
            raise ValueError("unknown agent")
        claim_token = secrets.token_urlsafe(32)
        deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
        with self._conn() as conn:
            self._assert_claim_budget(conn, agent_id)
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise ValueError("task not found")
            if row["status"] != TaskStatus.CREATED.value:
                raise ValueError("task not claimable")
            if row["capability_required"] not in agent["capabilities"]:
                raise ValueError("agent lacks capability")
            keys = row.keys()
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
            if row["task_type"] not in ("tester.run", "reviewer.approve"):
                lock_claim_stake(
                    conn,
                    agent_id=agent_id,
                    capability=row["capability_required"],
                    task_id=task_id,
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

            replication_status: str | None = None
            group_id = row["replication_group_id"] if "replication_group_id" in row.keys() else None
            if group_id:
                shared_payload = json.loads(
                    conn.execute(
                        "SELECT payload FROM replication_groups WHERE group_id = ?",
                        (group_id,),
                    ).fetchone()["payload"]
                )
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

        return SubmitResponse(
            submission_id=submission_id,
            replication_status=replication_status,
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
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, capability_required, status, payload,
                parent_task_id, parent_submission_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, capability_required, status, payload,
                parent_task_id, parent_submission_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    def get_agent_credibility(self, agent_id: str) -> list[dict[str, Any]] | None:
        if self.get_agent(agent_id) is None:
            return None
        with self._conn() as conn:
            return list_agent_credibility(conn, agent_id)

    def get_replication_group_status(self, group_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return get_replication_group(conn, group_id)

    def get_credibility_leaderboard(
        self, capability: str | None, limit: int
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return credibility_leaderboard(conn, capability, limit)

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
        return TaskEnvelope(
            task_id=row["task_id"],
            task_type=row["task_type"],
            capability_required=row["capability_required"],
            status=TaskStatus(row["status"]),
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
            parent_task_id=row["parent_task_id"],
        )

    def _row_to_verification(self, row: sqlite3.Row) -> VerificationEnvelope:
        return VerificationEnvelope(
            verification_id=row["verification_id"],
            submission_id=row["submission_id"],
            task_id=row["task_id"],
            task_type=row["task_type"],
            status=VerificationStatus(row["status"]),
            result_summary=json.loads(row["result_summary"]),
        )
